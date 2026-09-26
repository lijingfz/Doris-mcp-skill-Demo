#!/usr/bin/env python3
"""MCP smoke client: list tools / call a tool over streamable HTTP or a stdio command.

Examples:
  mcp_smoke.py --url http://127.0.0.1:8000/mcp list
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN call doris___net_check '{}'
  mcp_smoke.py --stdio "uvx mcp-proxy-for-aws@latest $RUNTIME_URL --service bedrock-agentcore --region us-east-1" list

The bearer token is read from the named environment variable and never printed.
Exit code: 0 on success, 1 when a tool call returns an error or a check fails.
"""

import argparse
import asyncio
import json
import os
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


COMMANDS = {"list": cmd_list, "call": cmd_call}


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
    args = parser.parse_args(argv)

    start = time.monotonic()
    async with build_client(args) as client:
        print(f"connected+initialized in {round((time.monotonic() - start) * 1000)} ms")
        rc = await COMMANDS[args.command](client, args)
    print(f"total {round((time.monotonic() - start) * 1000)} ms")
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
