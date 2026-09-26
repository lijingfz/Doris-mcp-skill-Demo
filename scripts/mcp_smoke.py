#!/usr/bin/env python3
"""MCP smoke client: list tools / call a tool over streamable HTTP or a stdio command.

Examples:
  mcp_smoke.py --url http://127.0.0.1:8000/mcp list
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN call doris___net_check '{}'
  mcp_smoke.py --stdio "uvx mcp-proxy-for-aws@latest $RUNTIME_URL --service bedrock-agentcore --region us-east-1" list
  mcp_smoke.py --url http://127.0.0.1:8000/mcp flow                       # profile flow + error cases
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN flow --prefix doris___

The bearer token is read from the named environment variable and never printed.
Exit code: 0 on success, 1 when a tool call returns an error or a check fails.
"""

import argparse
import asyncio
import json
import os
import secrets
import shlex
import sys
import time

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport


def build_client(args: argparse.Namespace) -> Client:
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


COMMANDS = {"list": cmd_list, "call": cmd_call, "flow": cmd_flow}


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--url", help="streamable HTTP MCP endpoint")
    target.add_argument("--stdio", help="command line of a stdio MCP server / proxy")
    parser.add_argument("--bearer-env", help="env var holding a bearer token (HTTP only)")
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
    args = parser.parse_args(argv)

    start = time.monotonic()
    async with build_client(args) as client:
        print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
        rc = await COMMANDS[args.command](client, args)
    print(f"total {round((time.monotonic() - start) * 1000)} ms")
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
