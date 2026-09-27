"""Offline tests for doris/permission_matrix.py (no Doris connection).

    .venv/bin/python -m unittest discover -s doris/test -v

The connection is a fake that answers by SQL prefix; SHOW GRANTS rows have the shape Doris 4.1
returns (checked as demo_ro in P2 planning). The live run is T2.3: read-only checks first, the
probes only after the GATE.
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

import pymysql  # noqa: E402

import permission_matrix  # noqa: E402
from agentcore_ext.settings import load_settings  # noqa: E402
from permission_matrix import classify_error, grant_problems, parse_grants, write_probes  # noqa: E402
from store.bootstrap import collect_physical_tables  # noqa: E402

from fastmcp import Client, FastMCP  # noqa: E402

MODELS = ROOT / "doris" / "semantic" / "ecom"
PASSWORD = "SvcPw0123456789abcXYZ"
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": PASSWORD}
IDENTITY = "'mcp_svc'@'%'"


def grants_row(database_privs, **columns):
    row = {"UserIdentity": IDENTITY, "Comment": "", "Password": "Yes", "RequireSan": None, "Roles": "",
           "GlobalPrivs": None, "CatalogPrivs": None, "DatabasePrivs": database_privs, "TablePrivs": None,
           "ColPrivs": None, "ResourcePrivs": None, "CloudClusterPrivs": None, "CloudStagePrivs": None,
           "StorageVaultPrivs": None, "WorkloadGroupPrivs": "normal: Usage_priv", "ComputeGroupPrivs": None}
    row.update(columns)
    return row


DEFAULT_DBS = "internal.information_schema: Select_priv; internal.mysql: Select_priv"
MCP_SVC_GRANTS = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}; internal.system_mcp: Select_priv,Create_priv")
DEMO_RO_GRANTS = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}", UserIdentity="'demo_ro'@'%'")


def denied(action="LOAD"):
    # Doris 4.1 refuses with errno 1105, not MySQL's 1142 (seen for every T2.3 probe).
    return pymysql.err.OperationalError(
        1105, f"errCode = 2, detailMessage = {action} command denied to user 'mcp_svc'@'10.0.0.9' for table 'x'")


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append(sql)
        response = self.conn.default
        for key in sorted(self.conn.responses, key=len, reverse=True):
            if sql.startswith(key):
                response = self.conn.responses[key]
                break
        if isinstance(response, BaseException):
            raise response
        self.rows = [dict(r) for r in response]

    def fetchall(self):
        return self.rows


class FakeDoris:
    """Answers by the longest matching SQL prefix; anything else gets `default` (a write denial)."""

    def __init__(self, overrides=None, default=None):
        self.responses = {
            "SELECT CURRENT_USER()": [{"identity": IDENTITY}],
            "SHOW GRANTS": [MCP_SVC_GRANTS],
            "SHOW DATABASES": [{"Database": d} for d in ("ecom", "information_schema", "mysql", "system_mcp")],
            "SHOW PROPERTY": [{"Key": "max_user_connections", "Value": "100"}, {"Key": "query_timeout", "Value": "-1"}],
            "SELECT 1 FROM ": [{"1": 1}],
            "SELECT semantic_version FROM system_mcp.workspace_metadata": [{"semantic_version": 2}],
            "SELECT COUNT(*) AS files FROM system_mcp.active_store_ecom": [{"files": 10}],
        }
        self.responses.update(overrides or {})
        self.default = default if default is not None else denied()
        self.executed, self.closed = [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def run_main(argv=(), env=ENV, conn=None, apply=False, store_init=None, connect=None):
    out, err, seen = io.StringIO(), io.StringIO(), {"connect": {}, "store_init": []}
    conn = conn or FakeDoris()
    env = dict(env, **({"APPLY": "1"} if apply else {}))

    def fake_connect(**kwargs):
        seen["connect"] = kwargs
        return conn

    def fake_store_init(settings, workspace):
        seen["store_init"].append((settings.doris_user, workspace))
        return store_init or (True, "discover_workspaces -> ecom; tables ensured")

    rc = permission_matrix.main(list(argv), env=env, connect=connect or fake_connect, out=out, err=err,
                                store_init=fake_store_init)
    return rc, out.getvalue(), err.getvalue(), conn, seen


class ParseGrants(unittest.TestCase):
    def test_parses_the_doris_show_grants_row(self):
        self.assertEqual(parse_grants(DEMO_RO_GRANTS), {
            "DatabasePrivs": {"internal.ecom": {"Select_priv"}, "internal.information_schema": {"Select_priv"},
                              "internal.mysql": {"Select_priv"}},
            "WorkloadGroupPrivs": {"normal": {"Usage_priv"}},
        })

    def test_several_privileges_with_or_without_spaces(self):
        for privs in ("Select_priv,Create_priv", "Select_priv, Create_priv"):
            with self.subTest(privs=privs):
                parsed = parse_grants({"DatabasePrivs": f"internal.system_mcp: {privs}"})
                self.assertEqual(parsed, {"DatabasePrivs": {"internal.system_mcp": {"Select_priv", "Create_priv"}}})

    def test_global_privileges_and_roles_have_no_object(self):
        parsed = parse_grants({"GlobalPrivs": "Node_priv,Admin_priv", "Roles": "operator", "TablePrivs": ""})
        self.assertEqual(parsed, {"GlobalPrivs": {"*": {"Node_priv", "Admin_priv"}}, "Roles": {"*": {"operator"}}})

    def test_a_repeated_object_merges_instead_of_hiding_the_first_entry(self):
        # Overwriting would drop Load_priv here and let grant_problems pass an over-privileged account.
        parsed = parse_grants({"DatabasePrivs": "internal.ecom: Load_priv; internal.ecom: Select_priv"})
        self.assertEqual(parsed, {"DatabasePrivs": {"internal.ecom": {"Load_priv", "Select_priv"}}})

    def test_non_privilege_columns_are_ignored(self):
        parsed = parse_grants({"UserIdentity": IDENTITY, "Password": "Yes", "Comment": "x", "RequireSan": None})
        self.assertEqual(parsed, {})


class GrantProblems(unittest.TestCase):
    def test_the_r42_grants_pass(self):
        self.assertEqual(grant_problems(parse_grants(MCP_SVC_GRANTS)), [])

    def test_an_extra_privilege_is_reported(self):
        row = grants_row(f"internal.ecom: Select_priv,Load_priv; {DEFAULT_DBS}; "
                         "internal.system_mcp: Select_priv,Create_priv")
        self.assertEqual(grant_problems(parse_grants(row)), ["DatabasePrivs internal.ecom: unexpected Load_priv"])

    def test_a_missing_privilege_is_reported(self):
        row = grants_row(f"internal.ecom: Select_priv; {DEFAULT_DBS}; internal.system_mcp: Select_priv")
        self.assertEqual(grant_problems(parse_grants(row)), ["DatabasePrivs internal.system_mcp: missing Create_priv"])

    def test_extra_scopes_and_roles_are_reported(self):
        row = dict(MCP_SVC_GRANTS, GlobalPrivs="Admin_priv", Roles="admin",
                   TablePrivs="internal.dw.orders: Select_priv")
        self.assertEqual(grant_problems(parse_grants(row)), [
            "GlobalPrivs *: unexpected Admin_priv",
            "Roles *: unexpected admin",
            "TablePrivs internal.dw.orders: unexpected Select_priv",
        ])

    def test_demo_ro_lacks_system_mcp(self):
        self.assertEqual(grant_problems(parse_grants(DEMO_RO_GRANTS)),
                         ["DatabasePrivs internal.system_mcp: missing Create_priv, Select_priv"])


class ClassifyError(unittest.TestCase):
    def test_privilege_error_codes_are_denials(self):
        for errno in (1044, 1142, 1143, 1227):
            with self.subTest(errno=errno):
                self.assertEqual(classify_error(pymysql.err.OperationalError(errno, "no")), "denied")

    def test_doris_generic_errors_that_say_denied_are_denials(self):
        # Seen as demo_ro: (1105, "... SHOW CREATE TABLE command denied to user 'demo_ro'@'...' for table ...")
        for message in ("errCode = 2, detailMessage = SHOW CREATE TABLE command denied to user 'demo_ro'@'x'",
                        "errCode = 2, detailMessage = Access denied; you need (at least one of) the (LOAD) "
                        "privilege(s) for this operation"):
            with self.subTest(message=message):
                self.assertEqual(classify_error(pymysql.err.OperationalError(1105, message)), "denied")

    def test_a_1105_needs_access_denied_or_command_denied(self):
        # errno 1105 is Doris's generic error: "denied" elsewhere in the text is not a privilege refusal.
        for message in ("errCode = 2, detailMessage = Unknown column 'denied_at' in 'ecom.fact_order'",
                        "errCode = 2, detailMessage = Permission denied: /opt/doris/fe/doris-meta"):
            with self.subTest(message=message):
                self.assertEqual(classify_error(pymysql.err.OperationalError(1105, message)), "error")

    def test_other_errors_are_not_denials(self):
        for errno, message in ((1105, "errCode = 2, detailMessage = Unknown table 'mcp_perm_probe'"),
                               (1064, "errCode = 2, detailMessage = Syntax error"),
                               # A login failure says "denied" too, but it is not Doris refusing the write.
                               (1045, "Access denied for user 'mcp_svc'@'x' (using password: YES)"),
                               (2013, "Lost connection to MySQL server during query")):
            with self.subTest(errno=errno):
                self.assertEqual(classify_error(pymysql.err.OperationalError(errno, message)), "error")


# A write probe must change nothing even if Doris allowed it (e.g. if R-42 were broken).
NO_OP_SHAPES = (
    r"INSERT INTO (\S+) SELECT \* FROM \1 WHERE 1 = 0",
    r"UPDATE \S+ SET (\w+) = \1 WHERE \w+ = 'mcp_perm_probe'",
    r"DELETE FROM \S+ WHERE \w+ = 'mcp_perm_probe'",
    r"DROP TABLE IF EXISTS \w+\.mcp_perm_probe",
    r"CREATE DATABASE IF NOT EXISTS ecom",  # exists
    r"GRANT SELECT_PRIV ON internal\.ecom\.\* TO '\w+'@'[^']+'",  # already held
    r"ADMIN SHOW FRONTEND CONFIG LIKE '[\w%]+'",  # read-only
)


class WriteProbes(unittest.TestCase):
    def test_every_write_probe_is_a_no_op_if_it_were_allowed(self):
        for probe in write_probes(IDENTITY):
            with self.subTest(probe=probe.name):
                self.assertEqual(sum(bool(re.fullmatch(s, probe.sql)) for s in NO_OP_SHAPES), 1, probe.sql)

    def test_probes_cover_load_create_drop_grant_and_admin(self):
        verbs = {p.sql.split()[0] for p in write_probes(IDENTITY)}
        self.assertEqual(verbs, {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "GRANT", "ADMIN"})
        targets = " ".join(p.sql for p in write_probes(IDENTITY))
        for schema in ("ecom.", "system_mcp."):
            self.assertIn(f"INSERT INTO {schema}", targets)
            self.assertIn(f"DROP TABLE IF EXISTS {schema}", targets)

    def test_names_are_unique(self):
        names = [p.name for p in write_probes(IDENTITY)]
        self.assertEqual(len(names), len(set(names)))

    def test_grant_probe_targets_the_connected_identity(self):
        grant = [p for p in write_probes("'mcp_svc'@'172.31.%'") if p.sql.startswith("GRANT")]
        self.assertEqual([p.sql for p in grant], ["GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%'"])


class DryRun(unittest.TestCase):
    def test_runs_only_read_only_statements_and_lists_the_probes(self):
        rc, out, err, conn, seen = run_main()
        self.assertEqual(rc, 0, err)
        self.assertEqual({s.split()[0] for s in conn.executed}, {"SELECT", "SHOW"})
        self.assertEqual(seen["store_init"], [])
        self.assertTrue(conn.closed)
        for line in (f"connected as {IDENTITY}", "ok    grants", "ok    databases: ecom, information_schema, "
                     "mysql, system_mcp", "ok    select: 9 physical tables", "ok    semantic store: workspace ecom "
                     "semantic_version=2, 10 active files", "info  max_user_connections=100",
                     "DRY-RUN probes", "4/4 checks pass"):
            self.assertIn(line, out)
        for probe in write_probes(IDENTITY):
            self.assertIn(probe.sql, out)
        self.assertIn("store_init", out)

    def test_select_covers_every_physical_table_of_the_models(self):
        _, _, _, conn, _ = run_main()
        selected = [s[len("SELECT 1 FROM "):-len(" LIMIT 1")] for s in conn.executed if s.startswith("SELECT 1 FROM")]
        self.assertEqual(selected, sorted(collect_physical_tables(MODELS)))
        self.assertIn("internal.ecom.v_paid_order", selected)

    def test_grant_mismatch_fails_and_the_other_checks_still_run(self):
        row = grants_row(f"internal.ecom: Select_priv,Load_priv; {DEFAULT_DBS}; "
                         "internal.system_mcp: Select_priv,Create_priv")
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW GRANTS": [row]}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  grants: DatabasePrivs internal.ecom: unexpected Load_priv", out)
        self.assertIn("ok    semantic store", out)
        self.assertIn("3/4 checks pass", out)

    def test_visible_databases_must_be_exactly_the_expected_ones(self):
        dbs = [{"Database": d} for d in ("dw", "ecom", "information_schema", "mysql")]
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW DATABASES": dbs}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  databases: missing system_mcp; unexpected dw", out)

    def test_an_unreadable_table_fails(self):
        conn = FakeDoris({"SELECT 1 FROM internal.ecom.dim_brand": denied("SELECT")})
        rc, out, _, _, _ = run_main(conn=conn)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  select: internal.ecom.dim_brand: 1105 SELECT command denied", out)

    def test_missing_metadata_row_fails_with_a_hint(self):
        # Upstream would INSERT the row on first use, which needs LOAD_PRIV: T2.5 must publish first.
        rc, out, _, conn, _ = run_main(conn=FakeDoris({"SELECT semantic_version FROM system_mcp.workspace_metadata": []}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  semantic store: no workspace_metadata row for ecom", out)
        self.assertIn("T2.5", out)

    def test_empty_active_store_fails(self):
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SELECT COUNT(*) AS files FROM system_mcp.active_store_ecom":
                                                    [{"files": 0}]}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  semantic store: workspace ecom has no active files", out)

    def test_a_check_that_errors_is_reported_by_name_and_the_rest_still_run(self):
        rc, out, _, _, _ = run_main(conn=FakeDoris({"SHOW GRANTS": denied("SHOW")}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  grants: 1105 SHOW command denied", out)
        self.assertIn("ok    databases", out)
        self.assertIn("3/4 checks pass", out)

    def test_long_messages_are_masked_before_they_are_cut(self):
        # Cutting first would keep a prefix of the password that the mask no longer recognises.
        leak = pymysql.err.OperationalError(1105, "SELECT command denied " + "x" * 130 + PASSWORD)
        rc, out, err, _, _ = run_main(conn=FakeDoris({"SELECT 1 FROM internal.ecom.dim_brand": leak}))
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD[:8], out + err)
        self.assertIn("x***", out)

    def test_show_property_failure_is_only_informational(self):
        rc, out, err, _, _ = run_main(conn=FakeDoris({"SHOW PROPERTY": denied("SHOW")}))
        self.assertEqual(rc, 0, err)
        self.assertIn("info  max_user_connections=unavailable (1105", out)

    def test_another_account_is_a_usage_error(self):
        conn = FakeDoris({"SELECT CURRENT_USER()": [{"identity": "'demo_ro'@'%'"}]})
        rc, _, err, _, _ = run_main(conn=conn)
        self.assertEqual(rc, 2)
        self.assertIn("mcp_svc", err)
        self.assertEqual(conn.executed, ["SELECT CURRENT_USER() AS identity"])

    def test_configuration_errors_are_usage_errors(self):
        for argv, env, text in (([], {"DORIS_USER": "mcp_svc", "DORIS_PASSWORD": PASSWORD}, "DORIS_HOST"),
                                (["--workspace", "ecom; DROP"], ENV, "workspace")):
            with self.subTest(text=text):
                rc, _, err, conn, seen = run_main(argv, env=env)
                self.assertEqual(rc, 2)
                self.assertIn(text, err)
                self.assertEqual((conn.executed, seen["connect"]), ([], {}))

    def test_connection_parameters(self):
        _, _, _, _, seen = run_main()
        kwargs = seen["connect"]
        self.assertEqual((kwargs["host"], kwargs["port"], kwargs["user"], kwargs["password"]),
                         ("10.0.0.1", 9030, "mcp_svc", PASSWORD))
        self.assertIs(kwargs["cursorclass"], pymysql.cursors.DictCursor)
        self.assertTrue(kwargs["autocommit"])

    def test_an_unexpected_error_is_one_masked_line_and_exit_2(self):
        conn = FakeDoris({"SELECT CURRENT_USER()": RuntimeError(f"cursor broke on 10.0.0.1 ({PASSWORD})")})
        rc, out, err, conn, _ = run_main(conn=conn)
        self.assertEqual(rc, 2)
        self.assertEqual(err.strip(), "FAILED: RuntimeError: cursor broke on *** (***)")
        self.assertNotIn(PASSWORD, out + err)
        self.assertTrue(conn.closed)

    def test_connect_errors_are_masked(self):
        def refuse(**kwargs):
            raise pymysql.err.OperationalError(1045, f"Access denied for 'mcp_svc' on 10.0.0.1 using {PASSWORD}")

        rc, out, err, _, _ = run_main(connect=refuse)
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)
        self.assertIn("***", err)


class Apply(unittest.TestCase):
    def test_all_writes_denied_and_store_init_ok_passes(self):
        rc, out, err, conn, seen = run_main(apply=True)
        self.assertEqual(rc, 0, err)
        self.assertEqual(seen["store_init"], [("mcp_svc", "ecom")])
        probes = write_probes(IDENTITY)
        for probe in probes:
            self.assertEqual(conn.executed.count(probe.sql), 1, probe.sql)
            self.assertIn(f"ok    probe {probe.name}: denied (1105 LOAD command denied", out)
        self.assertIn("ok    probe store_init: discover_workspaces -> ecom", out)
        total = 4 + 1 + len(probes)
        self.assertIn(f"{total}/{total} checks pass", out)
        self.assertNotIn("DRY-RUN", out)

    def test_a_failed_read_only_check_skips_store_init_and_the_probes(self):
        # A wrong account (e.g. with LOAD_PRIV) must not get its writes tried: the probes are no-ops only
        # when the read-only checks hold.
        row = grants_row(f"internal.ecom: Select_priv,Load_priv; {DEFAULT_DBS}; "
                         "internal.system_mcp: Select_priv,Create_priv")
        rc, out, _, conn, seen = run_main(conn=FakeDoris({"SHOW GRANTS": [row]}), apply=True)
        self.assertEqual(rc, 1)
        self.assertEqual(seen["store_init"], [])
        self.assertEqual({s.split()[0] for s in conn.executed}, {"SELECT", "SHOW"})
        self.assertIn("SKIPPED probes: 1 read-only check(s) failed; store_init and the write probes did not run", out)
        self.assertIn("3/4 checks pass", out)

    def test_an_allowed_write_fails(self):
        conn = FakeDoris({"INSERT INTO ecom.dim_brand": []})
        rc, out, _, _, _ = run_main(conn=conn, apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe load_ecom: ALLOWED, expected denied", out)

    def test_any_other_error_is_inconclusive(self):
        conn = FakeDoris({"DROP TABLE IF EXISTS ecom.": pymysql.err.OperationalError(1105, "Unknown table")})
        rc, out, _, _, _ = run_main(conn=conn, apply=True)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe drop_ecom: inconclusive, expected denied: 1105 Unknown table", out)

    def test_store_init_failure_fails(self):
        rc, out, _, _, _ = run_main(apply=True, store_init=(False, "Table init failed: CREATE command denied"))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe store_init: Table init failed: CREATE command denied", out)

    def test_store_init_database_error_is_caught_and_the_probes_still_run(self):
        def broken(settings, workspace):
            raise pymysql.err.OperationalError(1044, "Access denied for user 'mcp_svc' to database 'system_mcp'")

        out = io.StringIO()
        conn = FakeDoris()
        rc = permission_matrix.main([], env=dict(ENV, APPLY="1"), connect=lambda **kw: conn, out=out,
                                    err=io.StringIO(), store_init=broken)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  probe store_init: 1044", out.getvalue())
        self.assertIn("ok    probe admin", out.getvalue())

    def test_probe_messages_are_masked(self):
        leak = pymysql.err.OperationalError(1142, f"LOAD command denied ({PASSWORD} @ 10.0.0.1)")
        rc, out, err, _, _ = run_main(conn=FakeDoris(default=leak), apply=True)
        self.assertEqual(rc, 0, err)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)


class FakeStoreClass:
    """Stands in for store.store.DorisStore: class-level table cache, discover, logging init failure."""

    _table_cache: dict = {}
    workspaces = ["ecom"]
    fail = None

    @classmethod
    def discover_workspaces(cls):
        return list(cls.workspaces)

    def __init__(self, workspace):
        if self._table_cache.get(workspace):
            return
        if self.fail:
            logging.getLogger("doris_new_mcp.store").warning(
                f"Table init failed for workspace '{workspace}': {self.fail}")
        else:
            type(self)._table_cache[workspace] = True


class UpstreamStoreInit(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ENV)
        store = type("Store", (FakeStoreClass,), {"_table_cache": {}})
        self.store = store
        patches = {name: mock.patch.object(permission_matrix, name) for name in
                   ("set_doris_endpoint", "set_service_credentials", "clear_service_credentials")}
        patches["DorisStore"] = mock.patch.object(permission_matrix, "DorisStore", store)
        self.mocks = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

    def test_runs_upstream_init_as_the_service_account(self):
        ok, detail = permission_matrix.upstream_store_init(self.settings, "ecom")
        self.assertTrue(ok, detail)
        self.mocks["set_doris_endpoint"].assert_called_once_with("10.0.0.1", 9030)
        self.mocks["set_service_credentials"].assert_called_once_with("mcp_svc", PASSWORD)
        self.mocks["clear_service_credentials"].assert_called_once_with()
        self.assertTrue(self.store._table_cache["ecom"])

    def test_a_cached_success_cannot_hide_a_failure(self):
        self.store._table_cache["ecom"] = True
        self.store.fail = "(1142, 'CREATE command denied to user mcp_svc')"
        ok, detail = permission_matrix.upstream_store_init(self.settings, "ecom")
        self.assertFalse(ok)
        self.assertIn("CREATE command denied", detail)

    def test_an_undiscovered_workspace_fails(self):
        self.store.workspaces = []
        ok, detail = permission_matrix.upstream_store_init(self.settings, "ecom")
        self.assertFalse(ok)
        self.assertIn("discover_workspaces found []", detail)

    def test_credentials_are_cleared_when_discovery_raises(self):
        with mock.patch.object(self.store, "discover_workspaces",
                               side_effect=pymysql.err.OperationalError(1044, "denied")):
            with self.assertRaises(pymysql.MySQLError):
                permission_matrix.upstream_store_init(self.settings, "ecom")
        self.mocks["clear_service_credentials"].assert_called_once_with()


RUNTIME_URL = "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn/invocations?qualifier=DEFAULT"
VPC_IDENTITY = "'mcp_svc'@'172.31.%'"


def runtime_server(doris: FakeDoris) -> FastMCP:
    """The deployed server's execute_query, answering from a FakeDoris the way upstream tools/query.py does."""
    mcp = FastMCP("fake-runtime")

    @mcp.tool
    async def execute_query(sql: str, database: str = "", max_rows: int = 0) -> str:
        cur = doris.cursor()
        try:
            cur.execute(sql)
        except pymysql.MySQLError as e:  # upstream: error_response(CONNECTION_ERROR, str(e))
            return json.dumps({"success": False, "error": {"code": "CONNECTION_ERROR", "message": str(e)}})
        return json.dumps({"success": True, "data": {"columns": [], "rows": cur.fetchall()}}, default=str)

    return mcp


class RemoteRuntime(unittest.TestCase):
    """--url: the read-only checks through the deployed Runtime, as mcp_svc from the VPC (P3 / T3.5)."""

    def run_remote(self, argv=(), doris=None, apply=False, remote_error=None):
        doris = doris or FakeDoris({"SELECT CURRENT_USER()": [{"identity": VPC_IDENTITY}]})
        remote_calls = []

        def remote_connect(url, region):
            remote_calls.append((url, region))
            if remote_error:
                raise remote_error
            return permission_matrix.RuntimeConnection(Client(runtime_server(doris)))

        def no_direct_connect(**kwargs):
            raise AssertionError("--url must not connect to Doris directly")

        out, err = io.StringIO(), io.StringIO()
        env = {"APPLY": "1"} if apply else {}  # no DORIS_* at all: the Runtime has its own settings
        rc = permission_matrix.main(["--url", RUNTIME_URL, *argv], env=env, connect=no_direct_connect, out=out,
                                    err=err, remote_connect=remote_connect)
        return rc, out.getvalue(), err.getvalue(), doris, remote_calls

    def test_read_only_checks_run_through_the_runtime(self):
        rc, out, err, doris, remote_calls = self.run_remote(["--expect-host", "172.31.%"])
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(remote_calls, [(RUNTIME_URL, None)])
        self.assertEqual({s.split()[0] for s in doris.executed}, {"SELECT", "SHOW"})
        for line in (f"connected as {VPC_IDENTITY} (through the Runtime)", f"ok    identity: {VPC_IDENTITY}",
                     "ok    grants", "ok    databases", "ok    select: 9 physical tables", "ok    semantic store",
                     "info  max_user_connections=100", "5/5 checks pass"):
            self.assertIn(line, out)

    def test_params_are_inlined_as_literals(self):
        _, _, _, doris, _ = self.run_remote()
        self.assertIn("SELECT semantic_version FROM system_mcp.workspace_metadata WHERE workspace = 'ecom'",
                      doris.executed)

    def test_the_old_identity_fails_the_host_check(self):
        doris = FakeDoris()  # still 'mcp_svc'@'%'
        rc, out, _, _, _ = self.run_remote(["--expect-host", "172.31.%"], doris=doris)
        self.assertEqual(rc, 1)
        self.assertIn(f"FAIL  identity: connected as {IDENTITY}, expected {VPC_IDENTITY}", out)

    def test_doris_errors_keep_their_errno_and_ips_are_masked(self):
        doris = FakeDoris({"SELECT CURRENT_USER()": [{"identity": VPC_IDENTITY}],
                           "SELECT 1 FROM internal.ecom.fact_refund": denied("SELECT")})
        rc, out, err, _, _ = self.run_remote(doris=doris)
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"FAIL  select: internal\.ecom\.fact_refund: 1105 SELECT command denied to user 'mcp_svc'@'<ip>'")
        self.assertNotIn("10.0.0.9", out + err)

    def test_dry_run_lists_no_probes(self):
        rc, out, _, _, _ = self.run_remote()
        self.assertEqual(rc, 0, out)
        self.assertIn("probes: not run with --url", out)
        self.assertNotIn("DRY-RUN probes", out)

    def test_apply_with_url_is_a_usage_error(self):
        rc, _, err, doris, remote_calls = self.run_remote(apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("APPLY=1", err)
        self.assertEqual((doris.executed, remote_calls), ([], []))

    def test_region_is_passed_and_needs_url(self):
        _, _, _, _, remote_calls = self.run_remote(["--region", "us-east-1"])
        self.assertEqual(remote_calls, [(RUNTIME_URL, "us-east-1")])
        rc, _, err, _, _ = run_main(["--region", "us-east-1"])
        self.assertEqual(rc, 2)
        self.assertIn("--region only applies with --url", err)

    def test_a_session_failure_is_one_masked_line(self):
        rc, out, err, _, _ = self.run_remote(remote_error=ConnectionError("connect to 172.31.25.143:443 failed"))
        self.assertEqual(rc, 1)
        self.assertEqual(err.strip(), "FAILED: connect: ConnectionError: connect to <ip>:443 failed")
        self.assertEqual(out, "")

    def test_default_remote_connect_uses_the_sigv4_client(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import agentcore_client
        server = runtime_server(FakeDoris())
        with mock.patch.object(agentcore_client, "sigv4_client", return_value=Client(server)) as factory:
            conn = permission_matrix._runtime_connection(RUNTIME_URL, "us-east-1")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT CURRENT_USER() AS identity")
                    self.assertEqual(cur.fetchall(), [{"identity": IDENTITY}])
            finally:
                conn.close()
        factory.assert_called_once_with(RUNTIME_URL, "us-east-1")


class RuntimeCursor(unittest.TestCase):
    def cursor(self, body):
        return permission_matrix.RuntimeCursor(lambda sql: body)

    def test_a_non_mysql_tool_error_keeps_its_code(self):
        cur = self.cursor({"success": False, "error": {"code": "INVALID_SQL", "message": "Only read-only SQL"}})
        with self.assertRaises(pymysql.MySQLError) as cm:
            cur.execute("SELECT 1")
        self.assertEqual(cm.exception.args, (0, "INVALID_SQL: Only read-only SQL"))

    def test_a_mysql_error_message_becomes_errno_and_text(self):
        cur = self.cursor({"success": False, "error": {"code": "CONNECTION_ERROR",
                                                        "message": str(denied())}})
        with self.assertRaises(pymysql.MySQLError) as cm:
            cur.execute("SELECT 1")
        self.assertEqual(cm.exception.args[0], 1105)
        self.assertTrue(cm.exception.args[1].startswith("errCode = 2, detailMessage = LOAD command denied"))
        self.assertEqual(classify_error(cm.exception), "denied")

    def test_params_that_need_quoting_are_refused(self):
        cur = self.cursor({"success": True, "data": {"rows": []}})
        for bad in ("a'b", "x y", "", 3):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cur.execute("SELECT 1 WHERE w = %s", (bad,))

    def test_a_reply_that_is_not_a_result_is_an_error(self):
        with self.assertRaises(pymysql.MySQLError) as cm:
            self.cursor({"success": True}).execute("SELECT 1")
        self.assertIn("no rows", cm.exception.args[1])


class ExpectHostDirect(unittest.TestCase):
    def test_expect_host_also_checks_a_direct_connection(self):
        rc, out, err, _, _ = run_main(["--expect-host", "%"])
        self.assertEqual(rc, 0, err)
        self.assertIn(f"ok    identity: {IDENTITY}", out)
        self.assertIn("5/5 checks pass", out)


if __name__ == "__main__":
    unittest.main()
