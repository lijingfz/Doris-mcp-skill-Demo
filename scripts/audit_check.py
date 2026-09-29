#!/usr/bin/env python3
"""Count the doris_new_mcp.audit records in `aws logs filter-log-events` output (P3 / T3.3, R-32).

  aws logs filter-log-events --region us-east-1 --log-group-name "$LOG_GROUP" --start-time "$SINCE_MS" \\
      --filter-pattern '"doris_new_mcp.audit"' --output json \\
    | .venv/bin/python scripts/audit_check.py --calls scripts/smoke_calls.json --repeat 2 [--failures]

By default prints counts per tool and outcome only. With --failures it then lists every failed call in time
order: its tool, its error text (cut to 200 chars) and, for query_metric, its group_by / where / having, all
with IPv4 addresses masked as <ip>. Never SQL, other params, MetricFlow commands or client ids.
Exit code (the same with --failures: a failed call is still an audited one): 0 when every expected call is
audited, 1 when some are missing or a record is unreadable, 2 when the input is not filter-log-events JSON.
"""

import argparse
import json
import sys
from collections import Counter

import redact  # scripts/ is on sys.path when this file is run as a script
from mcp_smoke import load_calls

MARKER = "doris_new_mcp.audit: "
ERROR_CHARS = 200
FAILURE_PARAMS = {"query_metric": ("group_by", "where", "having")}  # the only params --failures shows


def parse_records(doc: dict) -> tuple[list[dict], int]:
    """The audit records of the log events, and how many audit lines could not be read."""
    records, unreadable = [], 0
    for event in doc.get("events") or []:
        message = str(event.get("message", ""))
        at = message.find(MARKER)
        if at < 0:
            continue
        try:
            record = json.loads(message[at + len(MARKER):])
        except ValueError:
            record = None
        if isinstance(record, dict) and isinstance(record.get("tool"), str):
            records.append(record)
        else:
            unreadable += 1
    return records, unreadable


def _one_line(value: object) -> str:
    """value on one line, IPv4 addresses masked (a CONNECTION_ERROR names the Doris host)."""
    return redact.redact(" ".join(str(value).split()), [])


def failure_lines(records: list[dict]) -> list[str]:
    """The --failures section: every failed call in time order, with its error and query_metric's filters."""
    failed = sorted((r for r in records if r.get("success") is not True), key=lambda r: str(r.get("timestamp", "")))
    lines = [f"failures: {len(failed)}"]
    for record in failed:
        error = _one_line(record["error"])[:ERROR_CHARS] if record.get("error") else "(not recorded)"
        lines.append(f"  {record.get('timestamp')}  {record['tool']}  {error}")
        params = record.get("params") if isinstance(record.get("params"), dict) else {}
        lines += [f"      {name}: {_one_line(params[name])}" for name in FAILURE_PARAMS.get(record["tool"], ())
                  if name in params]
    return lines


def main(argv: list[str] | None = None, stdin=sys.stdin, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calls", help="calls file of the smoke run (scripts/smoke_calls.json format)")
    parser.add_argument("--repeat", type=int, default=1, help="how many times the smoke run made each call")
    parser.add_argument("--failures", action="store_true",
                        help="also list each failed call: time, tool, error (IPv4-masked), query_metric filters")
    args = parser.parse_args(argv)

    def say(line: str) -> None:
        print(line, file=out)

    try:
        doc = json.load(stdin)
        if not isinstance(doc, dict):
            raise ValueError
    except ValueError:
        say("FAIL: input is not filter-log-events JSON (aws logs filter-log-events --output json)")
        return 2
    expected: Counter = Counter()
    if args.calls:
        for call in load_calls(args.calls):
            expected[call["tool"]] += args.repeat

    records, unreadable = parse_records(doc)
    ok = Counter(r["tool"] for r in records if r.get("success") is True)
    failed = Counter(r["tool"] for r in records if r.get("success") is not True)
    say(f"audit: {len(records)} records ({ok.total()} ok, {failed.total()} failed), {unreadable} unreadable")
    for tool in sorted(set(ok) | set(failed) | set(expected)):
        say(f"  {tool:<28} {ok[tool]:>3} ok {failed[tool]:>3} failed"
            + (f"  (expected >= {expected[tool]})" if tool in expected else ""))

    passed = True
    if expected:
        short = {t: n for t, n in sorted(expected.items()) if ok[t] + failed[t] < n}
        passed = not short
        detail = ", ".join(f"{t} {ok[t] + failed[t]}/{n}" for t, n in short.items())
        say(f"  [{'PASS' if passed else 'FAIL'}] every expected call audited: {len(expected) - len(short)}/"
            f"{len(expected)} tools" + (f" (short: {detail})" if short else ""))
    if unreadable:
        passed = False
        say(f"  [FAIL] unreadable audit records: {unreadable}")
    if args.failures:
        for line in failure_lines(records):
            say(line)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
