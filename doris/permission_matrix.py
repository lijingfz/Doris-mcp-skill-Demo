"""Check the Doris privileges of the MCP service account mcp_svc (P2 / T2.3; R-21, R-42).

    python doris/permission_matrix.py [--workspace ecom]           # read-only checks + the probe list
    APPLY=1 python doris/permission_matrix.py [--workspace ecom]   # GATE: also run the probes

Connection: agentcore_ext.settings.load_settings(os.environ) -- DORIS_HOST, DORIS_PORT and
DORIS_SECRET_ID=doris-mcp/mcp_svc (or DORIS_USER/DORIS_PASSWORD).
Read-only checks: SHOW GRANTS equals EXPECTED_GRANTS exactly (R-42), SHOW DATABASES equals
EXPECTED_DATABASES, every physical table of the models is readable, the workspace has a metadata
row (else upstream would INSERT it, which needs LOAD_PRIV) and active files.
Probes (APPLY=1): upstream's semantic-store init (CREATE ... IF NOT EXISTS) must pass as the service
account, and every write must be denied by Doris (R-21). Each write probe changes nothing even if it
were allowed: 0 rows, a missing row, IF EXISTS on an absent table, IF NOT EXISTS on an existing
database, a grant the account already holds, or a read-only ADMIN command.
Exit 0 when every check passes, 1 when one fails, 2 on usage/configuration errors.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"

import pymysql  # noqa: E402

from agentcore_ext.settings import Settings, SettingsError, load_settings  # noqa: E402
from store.bootstrap import collect_physical_tables  # noqa: E402
from store.store import (  # noqa: E402
    DorisStore, clear_service_credentials, set_doris_endpoint, set_service_credentials)

MASK = "***"
EXPECTED_USER = "mcp_svc"
EXPECTED_GRANTS: dict[str, dict[str, set[str]]] = {
    "DatabasePrivs": {
        "internal.ecom": {"Select_priv"},
        "internal.system_mcp": {"Select_priv", "Create_priv"},
        # Doris lists these for every user (demo_ro too): read-only system schemas.
        "internal.information_schema": {"Select_priv"},
        "internal.mysql": {"Select_priv"},
    },
    "WorkloadGroupPrivs": {"normal": {"Usage_priv"}},  # Doris default workload group
}
EXPECTED_DATABASES = frozenset({"ecom", "system_mcp", "information_schema", "mysql"})
DENIED_ERRNOS = frozenset({1044, 1142, 1143, 1227})
DENIED_1105 = ("access denied", "command denied")  # Doris 4.1 refuses privileges with errno 1105 (T2.3)
_WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule
_STORE_LOGGER = "doris_new_mcp.store"


@dataclasses.dataclass(frozen=True)
class Result:
    ok: bool
    name: str
    detail: str


@dataclasses.dataclass(frozen=True)
class Probe:
    name: str
    sql: str
    why: str


def write_probes(identity: str) -> list[Probe]:
    """Writes Doris must deny for `identity`; each is a no-op if it were allowed."""
    return [
        Probe("load_ecom", "INSERT INTO ecom.dim_brand SELECT * FROM ecom.dim_brand WHERE 1 = 0",
              "no LOAD_PRIV on ecom (0 rows)"),
        Probe("load_system_mcp", "INSERT INTO system_mcp.workspace_metadata "
              "SELECT * FROM system_mcp.workspace_metadata WHERE 1 = 0", "no LOAD_PRIV on system_mcp (0 rows)"),
        Probe("update_system_mcp", "UPDATE system_mcp.workspace_metadata SET semantic_version = semantic_version "
              "WHERE workspace = 'mcp_perm_probe'", "no LOAD_PRIV on system_mcp (no such row)"),
        Probe("delete_system_mcp", "DELETE FROM system_mcp.staging_store_ecom WHERE filename = 'mcp_perm_probe'",
              "no LOAD_PRIV on system_mcp (no such row)"),
        Probe("create_ecom", "CREATE DATABASE IF NOT EXISTS ecom", "no CREATE_PRIV on ecom (exists)"),
        Probe("drop_ecom", "DROP TABLE IF EXISTS ecom.mcp_perm_probe", "no DROP_PRIV on ecom (absent table)"),
        Probe("drop_system_mcp", "DROP TABLE IF EXISTS system_mcp.mcp_perm_probe",
              "no DROP_PRIV on system_mcp (absent table)"),
        Probe("grant", f"GRANT SELECT_PRIV ON internal.ecom.* TO {identity}", "no GRANT_PRIV (already held)"),
        Probe("admin", "ADMIN SHOW FRONTEND CONFIG LIKE 'qe_max_connection'", "no ADMIN_PRIV (read-only)"),
    ]


def parse_grants(row: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
    """{column: {object: privileges}} of the non-empty *Privs columns and Roles of a SHOW GRANTS row."""
    parsed: dict[str, dict[str, set[str]]] = {}
    for column, value in row.items():
        if not (column.endswith("Privs") or column == "Roles") or not value:
            continue
        scopes: dict[str, set[str]] = {}
        for entry in str(value).split(";"):
            obj, sep, privs = entry.strip().rpartition(": ")
            scopes.setdefault(obj if sep else "*", set()).update(p.strip() for p in privs.split(",") if p.strip())
        parsed[column] = scopes
    return parsed


def grant_problems(actual: Mapping[str, Mapping[str, set[str]]],
                   expected: Mapping[str, Mapping[str, set[str]]] = EXPECTED_GRANTS) -> list[str]:
    problems = []
    for column in sorted(actual.keys() | expected.keys()):
        got, want = actual.get(column, {}), expected.get(column, {})
        for obj in sorted(got.keys() | want.keys()):
            missing, extra = want.get(obj, set()) - got.get(obj, set()), got.get(obj, set()) - want.get(obj, set())
            if missing:
                problems.append(f"{column} {obj}: missing {', '.join(sorted(missing))}")
            if extra:
                problems.append(f"{column} {obj}: unexpected {', '.join(sorted(extra))}")
    return problems


def classify_error(error: pymysql.MySQLError) -> str:
    """'denied' for a privilege error, 'error' for anything else."""
    errno = error.args[0] if error.args else None
    message = str(error.args[1]) if len(error.args) > 1 else ""
    if errno in DENIED_ERRNOS or (errno == 1105 and any(d in message.lower() for d in DENIED_1105)):
        return "denied"
    return "error"


def _brief(error: pymysql.MySQLError, secrets: Iterable[str]) -> str:
    """errno + message, masked before it is cut (a cut secret no longer matches the mask)."""
    errno = error.args[0] if error.args else "?"
    message = str(error.args[1]) if len(error.args) > 1 else str(error)
    return f"{errno} {_mask(message.replace('errCode = 2, detailMessage = ', ''), secrets)[:160]}"


def _rows(cur: Any, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return list(cur.fetchall())


def check_grants(cur: Any) -> Result:
    rows = _rows(cur, "SHOW GRANTS")
    if len(rows) != 1:
        return Result(False, "grants", f"SHOW GRANTS returned {len(rows)} rows")
    problems = grant_problems(parse_grants(rows[0]))
    return Result(not problems, "grants", "; ".join(problems) or
                  "exactly internal.ecom SELECT, internal.system_mcp SELECT+CREATE (+ Doris defaults)")


def check_databases(cur: Any) -> Result:
    seen = {next(iter(r.values())) for r in _rows(cur, "SHOW DATABASES")}
    missing, extra = sorted(EXPECTED_DATABASES - seen), sorted(seen - EXPECTED_DATABASES)
    problems = ([f"missing {', '.join(missing)}"] if missing else []) + \
               ([f"unexpected {', '.join(extra)}"] if extra else [])
    return Result(not problems, "databases", "; ".join(problems) or ", ".join(sorted(seen)))


def check_select(cur: Any, tables: Sequence[str], secrets: Iterable[str]) -> Result:
    failed = []
    for table in tables:
        try:
            _rows(cur, f"SELECT 1 FROM {table} LIMIT 1")
        except pymysql.MySQLError as e:
            failed.append(f"{table}: {_brief(e, secrets)}")
    return Result(not failed, "select", "; ".join(failed) or f"{len(tables)} physical tables of the models")


def check_semantic_store(cur: Any, workspace: str) -> Result:
    rows = _rows(cur, "SELECT semantic_version FROM system_mcp.workspace_metadata WHERE workspace = %s",
                 (workspace,))
    if not rows:
        return Result(False, "semantic store", f"no workspace_metadata row for {workspace}: publish first (T2.5); "
                      "upstream would INSERT it, which needs LOAD_PRIV")
    files = _rows(cur, f"SELECT COUNT(*) AS files FROM system_mcp.active_store_{workspace}")[0]["files"]
    if not files:
        return Result(False, "semantic store", f"workspace {workspace} has no active files")
    return Result(True, "semantic store",
                  f"workspace {workspace} semantic_version={rows[0]['semantic_version']}, {files} active files")


def max_user_connections(cur: Any, secrets: Iterable[str]) -> str:
    try:
        props = {r["Key"]: r["Value"] for r in _rows(cur, "SHOW PROPERTY")}
    except pymysql.MySQLError as e:
        return f"unavailable ({_brief(e, secrets)})"
    return props.get("max_user_connections", "?")


def run_probe(cur: Any, probe: Probe, secrets: Iterable[str]) -> Result:
    name = f"probe {probe.name}"
    try:
        _rows(cur, probe.sql)
    except pymysql.MySQLError as e:
        if classify_error(e) == "denied":
            return Result(True, name, f"denied ({_brief(e, secrets)})")
        return Result(False, name, f"inconclusive, expected denied: {_brief(e, secrets)}")
    return Result(False, name, "ALLOWED, expected denied")


class _Messages(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def upstream_store_init(settings: Settings, workspace: str) -> tuple[bool, str]:
    """What every semantic tool call runs first, as the service account (service-credential mode)."""
    set_doris_endpoint(settings.doris_host, settings.doris_port)
    set_service_credentials(settings.doris_user, settings.doris_password)
    try:
        found = DorisStore.discover_workspaces()  # CREATE DATABASE IF NOT EXISTS system_mcp; SHOW TABLES
        if workspace not in found:
            return False, f"discover_workspaces found {sorted(found)}, not {workspace!r}"
        DorisStore._table_cache.pop(workspace, None)
        logger, handler = logging.getLogger(_STORE_LOGGER), _Messages()
        logger.addHandler(handler)
        try:
            DorisStore(workspace)  # CREATE DATABASE/TABLE IF NOT EXISTS, metadata SELECT; logs and swallows errors
        finally:
            logger.removeHandler(handler)
        if not DorisStore._table_cache.get(workspace):
            return False, "; ".join(handler.messages) or "table init failed"
        return True, f"discover_workspaces -> {workspace}; CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT ok"
    finally:
        clear_service_credentials()


def _mask(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, MASK)
    return text


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
         connect: Callable[..., Any] = pymysql.connect, out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         store_init: Callable[[Settings, str], tuple[bool, str]] = upstream_store_init) -> int:
    parser = argparse.ArgumentParser(description="Check the Doris privileges of mcp_svc.")
    parser.add_argument("--models", type=Path, default=MODELS_DIR, help="semantic YAML directory (tables)")
    parser.add_argument("--workspace", default="ecom", help="semantic workspace")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env

    if not _WORKSPACE_RE.match(args.workspace):
        print(f"ERROR: workspace must match {_WORKSPACE_RE.pattern}", file=err)
        return 2
    try:
        settings = load_settings(env)
    except SettingsError as e:
        print(f"ERROR: {e}", file=err)
        return 2
    tables = sorted(collect_physical_tables(args.models))
    secrets = [settings.doris_password, settings.doris_host]

    def emit(text: str, stream: TextIO = out) -> None:
        print(_mask(text, secrets), file=stream)

    try:
        conn = connect(host=settings.doris_host, port=settings.doris_port, user=settings.doris_user,
                       password=settings.doris_password, connect_timeout=10, read_timeout=60,
                       autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    except pymysql.MySQLError as e:
        emit(f"FAILED: connect: {e}", err)
        return 1
    results: list[Result] = []
    try:
        with conn.cursor() as cur:
            identity = _rows(cur, "SELECT CURRENT_USER() AS identity")[0]["identity"]
            if not identity.startswith(f"'{EXPECTED_USER}'@"):
                emit(f"ERROR: this checks {EXPECTED_USER}; connected as {identity}", err)
                return 2
            emit(f"connected as {identity}")
            checks: list[tuple[str, Callable[[Any], Result]]] = [
                ("grants", check_grants), ("databases", check_databases),
                ("select", lambda c: check_select(c, tables, secrets)),
                ("semantic store", lambda c: check_semantic_store(c, args.workspace))]
            for name, check in checks:
                try:
                    results.append(check(cur))
                except pymysql.MySQLError as e:
                    results.append(Result(False, name, _brief(e, secrets)))
                emit(_line(results[-1]))
            emit(f"info  max_user_connections={max_user_connections(cur, secrets)}")
            failed = sum(not r.ok for r in results)

            probes = write_probes(identity)
            if env.get("APPLY") != "1":
                emit("DRY-RUN probes (APPLY=1 to run; each write is a no-op if it were allowed):")
                emit(f"  store_init         expect ok      upstream DorisStore('{args.workspace}') as {EXPECTED_USER}: "
                     "CREATE DATABASE/TABLE IF NOT EXISTS + metadata SELECT")
                for probe in probes:
                    emit(f"  {probe.name:<18} expect denied  {probe.sql}   -- {probe.why}")
            elif failed:
                # The probes are no-ops only for the account the read-only checks describe.
                emit(f"SKIPPED probes: {failed} read-only check(s) failed; "
                     "store_init and the write probes did not run")
            else:
                try:
                    ok, detail = store_init(settings, args.workspace)
                except pymysql.MySQLError as e:
                    ok, detail = False, _brief(e, secrets)
                results.append(Result(ok, "probe store_init", detail))
                emit(_line(results[-1]))
                for probe in probes:
                    results.append(run_probe(cur, probe, secrets))
                    emit(_line(results[-1]))
    except pymysql.MySQLError as e:
        emit(f"FAILED: {_brief(e, secrets)}", err)
        return 1
    except Exception as e:  # noqa: BLE001 - one masked line instead of a traceback that may name the host
        emit(f"FAILED: {type(e).__name__}: {e}", err)
        return 2
    finally:
        conn.close()
    passed = sum(r.ok for r in results)
    emit(f"{passed}/{len(results)} checks pass")
    return 0 if passed == len(results) else 1


def _line(result: Result) -> str:
    return f"{'ok  ' if result.ok else 'FAIL'}  {result.name}: {result.detail}"


if __name__ == "__main__":
    sys.exit(main())
