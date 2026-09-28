#!/usr/bin/env python3
"""MCP smoke client: list tools / call a tool over streamable HTTP or a stdio command.

Examples:
  mcp_smoke.py --url http://127.0.0.1:8000/mcp list
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN call doris___net_check '{}'
  mcp_smoke.py --stdio "uvx mcp-proxy-for-aws@latest $RUNTIME_URL --service bedrock-agentcore --region us-east-1" list
  mcp_smoke.py --url http://127.0.0.1:8000/mcp flow                       # profile flow + error cases
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN flow --prefix doris___
  mcp_smoke.py --url "$RUNTIME_URL" --sigv4 list --expect 12          # Runtime directly, AWS_IAM inbound auth
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN time --prefix doris___ --parallel 20 --repeat 2
  mcp_smoke.py --url "$RUNTIME_URL" --sigv4 conns --expect-host-prefix 172.31.

The bearer token is read from the named environment variable and never printed. `time` and `conns`
print status, timings, error codes and counts only: never tool output, SQL results, hosts or statements.
A session or call that raises is one FAIL line with the URL and the token masked as *** and IPv4
addresses as <ip>; with --url the MCP SDK's own log lines go to stderr masked the same way
(scripts/redact.py).
Exit code: 0 on success, 1 when a tool call returns an error or a check fails, 2 on a bad calls file.
"""

import argparse
import asyncio
import json
import os
import secrets
import shlex
import sys
import time
from collections import Counter
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

import redact  # scripts/ is on sys.path when this file is run as a script

DEFAULT_CALLS = Path(__file__).resolve().parent / "smoke_calls.json"


def build_client(args: argparse.Namespace) -> Client:
    if args.sigv4:
        import agentcore_client  # scripts/ is on sys.path when this file is run as a script

        return agentcore_client.sigv4_client(args.url, args.region, timeout=args.timeout)
    if args.url:
        headers = {}
        if args.bearer_env:
            token = os.environ.get(args.bearer_env, "")
            if not token:
                sys.exit(f"environment variable {args.bearer_env} is empty")
            headers["Authorization"] = f"Bearer {token}"
        return Client(StreamableHttpTransport(args.url, headers=headers), timeout=args.timeout)
    cmd = shlex.split(args.stdio)
    return Client(StdioTransport(command=cmd[0], args=cmd[1:], env=dict(os.environ)), timeout=args.timeout)


def result_payload(result) -> object:
    """Return the tool result as JSON when possible, else the raw text."""
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except ValueError:
        return text


async def cmd_list(client: Client, args: argparse.Namespace) -> int:
    tools = await client.list_tools()
    for tool in sorted(tools, key=lambda t: t.name):
        ro = bool(tool.annotations and tool.annotations.readOnlyHint)
        print(f"  {tool.name}{'  [readOnly]' if ro else ''}")
    print(f"tools: {len(tools)}")
    if args.expect is not None and len(tools) != args.expect:
        print(f"FAIL: expected {args.expect} tools")
        return 1
    return 0


async def cmd_call(client: Client, args: argparse.Namespace) -> int:
    params = json.loads(args.params)
    result = await client.call_tool(args.tool, params, raise_on_error=False)
    print(json.dumps(result_payload(result), ensure_ascii=False, indent=2))
    return 1 if result.is_error else 0


async def call_json(client: Client, tool: str, params: dict) -> dict:
    payload = result_payload(await client.call_tool(tool, params, raise_on_error=False))
    return payload if isinstance(payload, dict) else {"success": False, "raw": payload}


def error_code(body: dict) -> str | None:
    return (body.get("error") or {}).get("code")


async def cmd_flow(client: Client, args: argparse.Namespace) -> int:
    """Profile flow (design §5.3) + the error cases of the P1 acceptance (design §11)."""
    p = args.prefix
    results: list[bool] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    token = secrets.token_hex(6)
    sql = f"SELECT /*+SET_VAR(enable_profile=true)*/ COUNT(*) AS n FROM {args.table} /* trace:{token} */"
    body = await call_json(client, f"{p}execute_query", {"sql": sql})
    check("execute_query with the profile hint", body.get("success") is True, error_code(body) or "")

    row = None
    deadline = time.monotonic() + args.wait
    while row is None and time.monotonic() < deadline:  # profiles are collected asynchronously
        body = await call_json(client, f"{p}list_recent_queries", {"sql_contains": token, "limit": 5})
        queries = (body.get("data") or {}).get("queries") or []
        row = queries[0] if queries else None
        if row is None:
            await asyncio.sleep(1)
    check("list_recent_queries finds the trace token", row is not None, error_code(body) or "")
    if row is not None:
        print(f"      query_id={row['query_id']} trace_comment_kept={f'trace:{token}' in row['sql']}")
        body = await call_json(client, f"{p}get_query_profile", {"query_id": row["query_id"]})
        data = body.get("data") or {}
        check(
            "get_query_profile summary < 20000 chars",
            data.get("profile_found") is True and data.get("returned_chars", 20000) < 20000,
            f"source={data.get('source')} total_chars={data.get('total_chars')} returned_chars={data.get('returned_chars')}",
        )

    body = await call_json(client, f"{p}get_query_profile", {"query_id": "../../api/x"})
    check("invalid query_id -> INVALID_PARAMS", error_code(body) == "INVALID_PARAMS")
    body = await call_json(client, f"{p}get_query_profile", {"query_id": "ffffffffffffffff-ffffffffffffffff"})
    check("unknown query_id -> profile_found=false",
          body.get("success") is True and (body.get("data") or {}).get("profile_found") is False)
    body = await call_json(client, f"{p}execute_query", {"sql": f"DELETE FROM {args.table} WHERE 1 = 0"})
    check("DML is rejected", body.get("success") is False, error_code(body) or "")
    print(f"flow: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


def load_calls(path: str | Path) -> list[dict]:
    """[{"tool": NAME, "params": {...}}, ...]; ValueError on any other shape."""
    calls = json.loads(Path(path).read_text())
    if not isinstance(calls, list) or not calls:
        raise ValueError("calls file must be a non-empty JSON list")
    for i, call in enumerate(calls, 1):
        if not (isinstance(call, dict) and isinstance(call.get("tool"), str) and call["tool"]
                and isinstance(call.get("params"), dict)):
            raise ValueError(f"calls file entry {i} needs a tool name and a params object")
    return calls


def _percentile(sorted_ms: list[int], pct: int) -> int:
    return sorted_ms[max(0, -(-len(sorted_ms) * pct // 100) - 1)]  # nearest rank


async def _timed_call(client: Client, tool: str, params: dict) -> str | None:
    """None when the call succeeded, else a short reason (error code or exception type, never a message)."""
    result = await client.call_tool(tool, params, raise_on_error=False)
    payload = result_payload(result)
    body = payload if isinstance(payload, dict) else {}
    if result.is_error:
        return error_code(body) or "tool error"
    if body.get("success") is False:
        return error_code(body) or "success=false"
    return None


async def cmd_time(args: argparse.Namespace, client_factory) -> int:
    """Time every call of the calls file; fail on an error or a call over --budget-ms."""
    try:
        calls = load_calls(args.calls)
    except (OSError, ValueError) as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 2
    work = [(f"{args.prefix}{c['tool']}", c["params"]) for _ in range(args.repeat) for c in calls]
    gate = asyncio.Semaphore(args.parallel)
    timings: list[int] = []
    errors = slow = 0

    async def one(shared: Client | None, tool: str, params: dict) -> None:
        nonlocal errors, slow
        async with gate:
            start = time.monotonic()
            try:
                if shared is not None:
                    reason = await _timed_call(shared, tool, params)
                else:  # a new MCP session per call, as the Gateway does; connect + initialize are timed too
                    async with client_factory(args) as client:
                        reason = await _timed_call(client, tool, params)
            except Exception as e:  # noqa: BLE001 - counted and reported by type only
                reason = type(e).__name__
            ms = round((time.monotonic() - start) * 1000)
        timings.append(ms)
        if reason is not None:
            errors += 1
            status = "ERR"
        elif ms > args.budget_ms:
            slow += 1
            status = "SLOW"
        else:
            status = "ok"
        print(f"  {status:<4} {ms:>6} ms  {tool}" + (f"  ({reason})" if reason else ""), flush=True)

    start = time.monotonic()
    if args.fresh:
        await asyncio.gather(*(one(None, tool, params) for tool, params in work))
    else:
        try:
            async with client_factory(args) as client:
                print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
                await asyncio.gather(*(one(client, tool, params) for tool, params in work))
        except Exception as e:  # noqa: BLE001 - never print the message: it may carry a host
            print(f"FAIL: session: {type(e).__name__}")
            return 1
    ordered = sorted(timings)
    mode = f"{args.parallel} parallel" + (", fresh session each" if args.fresh else "")
    print(f"time: {len(work)} calls ({mode}), {errors} errors, {slow} over {args.budget_ms} ms; "
          f"p50 {_percentile(ordered, 50)} ms, p95 {_percentile(ordered, 95)} ms, max {ordered[-1]} ms; "
          f"wall {round((time.monotonic() - start) * 1000)} ms")
    return 1 if errors or slow else 0


async def cmd_conns(client: Client, args: argparse.Namespace) -> int:
    """The service account's Doris connections, as counts (a non-admin sees only its own)."""
    body = await call_json(client, f"{args.prefix}execute_query", {"sql": "SHOW PROCESSLIST"})
    if body.get("success") is not True:
        print(f"FAIL: SHOW PROCESSLIST: {error_code(body) or 'no result'}")
        return 1
    rows = (body.get("data") or {}).get("rows") or []

    def seconds(row: dict) -> int:
        try:
            return int(float(row.get("Time") or 0))
        except (TypeError, ValueError):
            return 0

    commands = Counter(str(r.get("Command")) for r in rows)
    hosts = {str(r.get("Host", "")).rsplit(":", 1)[0] for r in rows}
    users = sorted({str(r.get("User")) for r in rows})
    idle = [seconds(r) for r in rows if r.get("Command") == "Sleep"]
    print(f"connections: {len(rows)} (" + ", ".join(f"{k} {v}" for k, v in sorted(commands.items()))
          + f") from {len(hosts)} distinct hosts; users {', '.join(users) or '-'}; max idle {max(idle, default=0)} s")
    ok = True
    if args.expect_host_prefix is not None:
        matched = sum(str(r.get("Host", "")).startswith(args.expect_host_prefix) for r in rows)
        passed = bool(rows) and matched == len(rows)
        ok &= passed
        print(f"  [{'PASS' if passed else 'FAIL'}] host prefix {args.expect_host_prefix}: {matched}/{len(rows)} connections")
    if args.max_idle is not None:
        over = sum(s > args.max_idle for s in idle)
        ok &= over == 0
        print(f"  [{'PASS' if over == 0 else 'FAIL'}] idle connections <= {args.max_idle} s: {over} over")
    return 0 if ok else 1


COMMANDS = {"list": cmd_list, "call": cmd_call, "flow": cmd_flow, "conns": cmd_conns}


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--url", help="streamable HTTP MCP endpoint")
    target.add_argument("--stdio", help="command line of a stdio MCP server / proxy")
    parser.add_argument("--bearer-env", help="env var holding a bearer token (HTTP only)")
    parser.add_argument("--sigv4", action="store_true",
                        help="sign requests with SigV4 for bedrock-agentcore (a Runtime invoke URL, AWS_* credentials)")
    parser.add_argument("--region", help="SigV4 region (default: taken from the --url host)")
    parser.add_argument("--timeout", type=float, default=90.0, help="per-request timeout seconds")
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="list tools")
    p_list.add_argument("--expect", type=int, help="fail unless exactly N tools are listed")
    p_call = sub.add_parser("call", help="call one tool")
    p_call.add_argument("tool")
    p_call.add_argument("params", nargs="?", default="{}", help="JSON object of arguments")
    p_flow = sub.add_parser("flow", help="profile flow + error cases against a Doris MCP")
    p_flow.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
    p_flow.add_argument("--table", default="ecom.fact_order", help="table the profiled COUNT(*) reads")
    p_flow.add_argument("--wait", type=float, default=15.0, help="seconds to wait for the profile to appear")
    p_time = sub.add_parser("time", help="time each call of a calls file (P3 latency / concurrency checks)")
    p_time.add_argument("--calls", default=str(DEFAULT_CALLS), help="JSON list of {tool, params} (default: %(default)s)")
    p_time.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
    p_time.add_argument("--parallel", type=_positive_int, default=1, help="calls in flight at once")
    p_time.add_argument("--repeat", type=_positive_int, default=1, help="run the calls file N times")
    p_time.add_argument("--fresh", action="store_true", help="new MCP session per call (timed with connect)")
    p_time.add_argument("--budget-ms", type=int, default=60000, help="fail any call slower than this")
    p_conns = sub.add_parser("conns", help="count the service account's Doris connections (SHOW PROCESSLIST)")
    p_conns.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
    p_conns.add_argument("--expect-host-prefix", help="fail unless every connection comes from hosts with this prefix")
    p_conns.add_argument("--max-idle", type=int, help="fail if any idle (Sleep) connection is older than N seconds")
    args = parser.parse_args(argv)
    if args.sigv4 and not args.url:
        parser.error("--sigv4 needs --url")
    if args.sigv4 and args.bearer_env:
        parser.error("--sigv4 and --bearer-env are mutually exclusive")
    if args.region and not args.sigv4:
        parser.error("--region only applies to --sigv4")
    return args


async def main(argv: list[str] | None = None, client_factory=build_client) -> int:
    args = parse_args(argv)
    hidden = [args.url, os.environ.get(args.bearer_env, "") if args.bearer_env else ""]
    if args.url:
        redact.redact_sdk_logs(hidden)
    start = time.monotonic()
    try:
        if args.command == "time":
            rc = await cmd_time(args, client_factory)
        else:
            async with client_factory(args) as client:
                print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
                rc = await COMMANDS[args.command](client, args)
    except Exception as e:  # noqa: BLE001 - one masked line instead of a traceback naming the URL
        print(f"FAIL: {type(e).__name__}: {redact.redact(str(e), hidden)}")
        rc = 1
    print(f"total {round((time.monotonic() - start) * 1000)} ms")
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
