#!/usr/bin/env python3
"""Per-minute latency of the Gateway's tools/call, from CloudWatch (P4 / T4.6, P0 review M-3).

Quick calls a Cloud Connector from its own backend, so the Gateway's InvokeGateway Latency is what Quick
waits for on each tool call: the number Quick's 60 s limit applies to.

  q=$(.venv/bin/python scripts/gw_latency.py queries --gateway-arn "$GW_ARN")
  aws cloudwatch get-metric-data --region us-east-1 --start-time "$FROM" --end-time "$TO" \\
      --metric-data-queries "$q" --output json \\
    | .venv/bin/python scripts/gw_latency.py report

Prints tool names, minutes, call counts and milliseconds only: never the ARN.
Exit code: 0 when every minute stays under --limit-ms (--warn-ms only flags), 1 when one does not or there
are no datapoints, 2 when the input is not get-metric-data JSON or --gateway-arn is not a Gateway ARN.
"""

import argparse
import json
import re
import sys

GATEWAY_ARN_RE = re.compile(r"arn:aws:bedrock-agentcore:[a-z0-9-]+:\d{12}:gateway/[A-Za-z0-9-]+")
STATS = (("calls", "SampleCount"), ("avg", "Average"), ("max", "Maximum"))


def queries(gateway_arn: str) -> list[dict]:
    """get-metric-data queries: one SEARCH per statistic over every tool, labelled with the tool name."""
    search = ("{AWS/Bedrock-AgentCore,Method,Name,Operation,Protocol,Resource} MetricName=\"Latency\" "
              f"Operation=\"InvokeGateway\" Method=\"tools/call\" Resource=\"{gateway_arn}\"")
    return [{"Id": id_, "Expression": f"SEARCH('{search}', '{stat}', 60)", "Label": "${PROP('Dim.Name')}"}
            for id_, stat in STATS]


def parse_rows(doc: dict) -> dict[tuple[str, str], dict[str, float]]:
    """{(minute, tool): {"calls": n, "avg": ms, "max": ms}} from the results of queries(); others are skipped."""
    rows: dict[tuple[str, str], dict[str, float]] = {}
    ids = {id_ for id_, _ in STATS}
    for result in doc["MetricDataResults"]:
        if result.get("Id") not in ids:
            continue
        for at, value in zip(result.get("Timestamps") or [], result.get("Values") or []):
            rows.setdefault((str(at)[:16], str(result.get("Label"))), {})[result["Id"]] = float(value)
    return rows


def main(argv: list[str] | None = None, stdin=sys.stdin, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("queries", help="print the --metric-data-queries JSON").add_argument("--gateway-arn", required=True)
    report = sub.add_parser("report", help="summarise get-metric-data JSON from stdin")
    report.add_argument("--warn-ms", type=float, default=45000, help="flag minutes at or above this (T5.5)")
    report.add_argument("--limit-ms", type=float, default=60000, help="fail minutes at or above this (Quick: 60 s)")
    args = parser.parse_args(argv)

    def say(line: str) -> None:
        print(line, file=out)

    if args.command == "queries":
        if not GATEWAY_ARN_RE.fullmatch(args.gateway_arn):
            say("FAIL: --gateway-arn is not a Gateway ARN")
            return 2
        say(json.dumps(queries(args.gateway_arn)))
        return 0

    try:
        doc = json.load(stdin)
        if not isinstance(doc, dict) or not isinstance(doc.get("MetricDataResults"), list):
            raise ValueError
    except ValueError:
        say("FAIL: input is not get-metric-data JSON (aws cloudwatch get-metric-data --output json)")
        return 2

    rows = sorted(parse_rows(doc).items())
    calls = sum(round(stats.get("calls", 0)) for _, stats in rows)
    if not rows:
        say("tools/call: 0 calls in 0 rows (tool x minute)")
        say("  [FAIL] no tools/call datapoints in the window")
        return 1
    (top_minute, top_tool), top = max(rows, key=lambda row: row[1].get("max", 0))
    say(f"tools/call: {calls} calls in {len(rows)} rows (tool x minute), "
        f"max {top.get('max', 0):.0f} ms ({top_tool} at {top_minute})")
    for (minute, tool), stats in rows:
        say(f"  {minute}  {tool:<36} {round(stats.get('calls', 0)):>3} calls  avg {stats.get('avg', 0):>7.0f} ms"
            f"  max {stats.get('max', 0):>7.0f} ms")

    def over(threshold: float) -> list[str]:
        return [f"{minute} {tool} {stats['max']:.0f} ms" for (minute, tool), stats in rows
                if stats.get("max", 0) >= threshold]

    slow = over(args.limit_ms)
    say(f"  [{'FAIL' if slow else 'PASS'}] every minute under {args.limit_ms:.0f} ms"
        + (f" ({len(slow)} not: {', '.join(slow)})" if slow else ""))
    if warned := over(args.warn_ms):
        say(f"  [WARN] >= {args.warn_ms:.0f} ms (T5.5: lower query_timeout): {', '.join(warned)}")
    return 1 if slow else 0


if __name__ == "__main__":
    sys.exit(main())
