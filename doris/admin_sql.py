"""Run a doris/*.sql account script as the Doris admin (design §6.1, P2 / T2.2).

Normally invoked through doris/apply-admin-sql.sh, which supplies stdin and the environment:
    <SecretString on stdin> | [APPLY=1] python doris/admin_sql.py doris/01_mcp_user.sql

stdin  Secrets Manager SecretString {"username": ..., "password": ...} of the service account
env    DORIS_HOST, DORIS_PORT (9030), DORIS_ADMIN_USER, DORIS_ADMIN_PASSWORD; APPLY=1 executes
The SQL may reference ${MCP_SVC_PASSWORD}; it is filled in memory only. Dry-run (default) prints the
statements with the password masked and never connects. Only account statements for the secret's
user are accepted: CREATE USER IF NOT EXISTS / ALTER USER ... IDENTIFIED BY / GRANT of SELECT_PRIV
and CREATE_PRIV on a single internal database.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

import pymysql

MASK = "***"
_PASSWORD_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_]+)\}")
_IDENT = r"(?P<ident>'(?P<user>[a-z_][a-z0-9_]*)'@'[0-9.%]+')"
_PRIV = r"(?:SELECT_PRIV|CREATE_PRIV)"
_ALLOWED = (
    re.compile(rf"^CREATE USER IF NOT EXISTS {_IDENT} IDENTIFIED BY '[^']*'$"),
    re.compile(rf"^ALTER USER {_IDENT} IDENTIFIED BY '[^']*'$"),
    re.compile(rf"^GRANT {_PRIV}(?:, {_PRIV})* ON internal\.[a-z_][a-z0-9_]*\.\* TO {_IDENT}$"),
)


class AdminSqlError(ValueError):
    """Rejected input; messages never contain secret values."""


def load_statements(text: str) -> list[str]:
    """Split on ';', drop '--' comment lines, collapse whitespace."""
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    return [" ".join(part.split()) for part in body.split(";") if part.strip()]


def _match(stmt: str) -> re.Match[str]:
    for pattern in _ALLOWED:
        m = pattern.match(stmt)
        if m:
            return m
    raise AdminSqlError(f"statement not allowed: {stmt}")


def render(statements: Sequence[str], values: Mapping[str, str]) -> list[str]:
    """Check every statement against the allowlist, then fill ${NAME} placeholders."""

    def fill(m: re.Match[str]) -> str:
        if m.group(1) not in values:
            raise AdminSqlError(f"unknown placeholder ${{{m.group(1)}}}")
        return values[m.group(1)]

    return [_PLACEHOLDER_RE.sub(fill, stmt) for stmt in statements if _match(stmt)]


def _read_secret(raw: str) -> tuple[str, str]:
    try:
        doc = json.loads(raw)
        user, password = doc["username"], doc["password"]
    except (ValueError, TypeError, KeyError):
        raise AdminSqlError("stdin must be the secret JSON with 'username' and 'password'") from None
    if not isinstance(user, str) or not isinstance(password, str) or not _PASSWORD_RE.match(password):
        raise AdminSqlError("the secret's password must be 16-128 letters/digits (see infra/40-doris-secret.sh)")
    return user, password


def _mask(text: str, secrets: Sequence[str]) -> str:
    for s in secrets:
        text = text.replace(s, MASK)
    return text


def main(
    argv: Sequence[str],
    stdin: TextIO = sys.stdin,
    env: Mapping[str, str] = os.environ,
    connect: Callable[..., Any] = pymysql.connect,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    if len(argv) != 1:
        print("usage: <secret JSON on stdin> | [APPLY=1] python doris/admin_sql.py FILE.sql", file=err)
        return 2
    try:
        statements = load_statements(Path(argv[0]).read_text(encoding="utf-8"))
        matches = [_match(s) for s in statements]
        user, password = _read_secret(stdin.read())
        targets = {m.group("user") for m in matches}
        if targets != {user}:
            raise AdminSqlError(f"the SQL targets {sorted(targets)} but the secret is for {user!r}")
        rendered = render(statements, {"MCP_SVC_PASSWORD": password})
    except (OSError, AdminSqlError) as e:
        print(f"ERROR: {e}", file=err)
        return 2
    identities = sorted({m.group("ident") for m in matches})
    shown = [_mask(s, [password]) for s in rendered]

    if env.get("APPLY") != "1":
        for s in shown:
            print(f"DRY-RUN SQL: {s}", file=out)
        print(f"DRY-RUN: {len(shown)} statements as {env.get('DORIS_ADMIN_USER') or '<admin>'}; "
              "APPLY=1 to execute", file=out)
        return 0

    missing = [k for k in ("DORIS_HOST", "DORIS_ADMIN_USER", "DORIS_ADMIN_PASSWORD") if not env.get(k)]
    if missing:
        print(f"ERROR: missing environment: {', '.join(missing)}", file=err)
        return 2
    secrets = [password, env["DORIS_ADMIN_PASSWORD"], env["DORIS_HOST"]]  # pymysql errors name the host
    try:
        conn = connect(host=env["DORIS_HOST"], port=int(env.get("DORIS_PORT") or 9030),
                       user=env["DORIS_ADMIN_USER"], password=env["DORIS_ADMIN_PASSWORD"],
                       connect_timeout=10, read_timeout=60, autocommit=True)
    except pymysql.MySQLError as e:
        print(f"FAILED: connect: {_mask(str(e), secrets)}", file=err)
        return 1
    try:
        with conn.cursor() as cur:
            for stmt, text in zip(rendered, shown):
                try:
                    cur.execute(stmt)
                except pymysql.MySQLError as e:
                    print(f"FAILED: {text}\n  {_mask(str(e), secrets)}", file=err)
                    return 1
                print(f"ok: {text}", file=out)
            for ident in identities:
                cur.execute(f"SHOW GRANTS FOR {ident}")
                for row in cur.fetchall():
                    print(f"grants: {_mask(' | '.join(map(str, row)), secrets)}", file=out)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
