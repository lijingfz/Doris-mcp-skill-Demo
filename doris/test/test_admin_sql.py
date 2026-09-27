"""Offline tests for doris/admin_sql.py (no Doris connection; a fake connect() records statements).

    .venv/bin/python -m unittest discover -s doris/test -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import admin_sql  # noqa: E402

PW = "Abc123def456GHI789jkl012MNO345pq"
SECRET = json.dumps({"username": "mcp_svc", "password": PW})
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_ADMIN_USER": "root", "DORIS_ADMIN_PASSWORD": "rootpw-xyz"}
SQL = """-- header comment
CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';
"""


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, stmt):
        self.conn.executed.append(stmt)
        if self.conn.fail_on and self.conn.fail_on in stmt:
            raise admin_sql.pymysql.MySQLError(1105, f"errCode = 2, detailMessage = bad statement: {stmt}")

    def fetchall(self):
        return (("'mcp_svc'@'%'", "Yes", "internal.ecom: Select_priv"),)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, fail_on=None):
        self.executed: list[str] = []
        self.fail_on = fail_on
        self.kwargs = {}

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass


def run(sql=SQL, secret=SECRET, env=None, apply=False, fail_on=None, connect_error=None):
    env = dict(ENV if env is None else env)
    if apply:
        env["APPLY"] = "1"
    conn = FakeConn(fail_on)

    def connect(**kwargs):
        conn.kwargs = kwargs
        if connect_error:
            raise connect_error
        return conn

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write(sql)
    out, err = io.StringIO(), io.StringIO()
    rc = admin_sql.main([f.name], stdin=io.StringIO(secret), env=env, connect=connect, out=out, err=err)
    Path(f.name).unlink()
    return rc, out.getvalue() + err.getvalue(), conn


class LoadStatements(unittest.TestCase):
    def test_splits_on_semicolons_and_drops_comment_lines(self):
        stmts = admin_sql.load_statements(SQL)
        self.assertEqual(len(stmts), 3)
        self.assertTrue(stmts[0].startswith("CREATE USER IF NOT EXISTS"))
        self.assertFalse(any("header comment" in s for s in stmts))


class Render(unittest.TestCase):
    def test_unknown_placeholder_is_an_error(self):
        with self.assertRaises(admin_sql.AdminSqlError):
            admin_sql.render(["ALTER USER 'x'@'%' IDENTIFIED BY '${OTHER}'"], {"MCP_SVC_PASSWORD": PW})

    def test_statement_outside_the_allowlist_is_rejected(self):
        for stmt in ("DROP USER 'mcp_svc'@'%'", "SET GLOBAL enable_profile = true", "SELECT 1",
                     "GRANT ADMIN_PRIV ON *.*.* TO 'mcp_svc'@'%'", "GRANT SELECT_PRIV ON *.*.* TO 'mcp_svc'@'%'"):
            with self.subTest(stmt=stmt), self.assertRaises(admin_sql.AdminSqlError):
                admin_sql.render([stmt], {})


class Main(unittest.TestCase):
    def test_dry_run_prints_masked_statements_and_never_connects(self):
        rc, output, conn = run()
        self.assertEqual(rc, 0)
        self.assertIn("DRY-RUN SQL: CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '***'", output)
        self.assertNotIn(PW, output)
        self.assertEqual(conn.executed, [])

    def test_apply_executes_rendered_statements_then_shows_grants(self):
        rc, output, conn = run(apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(conn.executed), 4)
        # Filled in memory (a literal password after IDENTIFIED BY would trip scripts/check-secrets.sh).
        self.assertEqual(conn.executed[0], admin_sql.load_statements(SQL)[0].replace("${MCP_SVC_PASSWORD}", PW))
        self.assertEqual(conn.executed[-1], "SHOW GRANTS FOR 'mcp_svc'@'%'")
        self.assertEqual(conn.kwargs["user"], "root")
        self.assertEqual(conn.kwargs["password"], "rootpw-xyz")
        self.assertNotIn(PW, output)
        self.assertNotIn("rootpw-xyz", output)

    def test_error_messages_are_masked_and_execution_stops(self):
        rc, output, conn = run(apply=True, fail_on="ALTER USER")
        self.assertEqual(rc, 1)
        self.assertEqual(len(conn.executed), 2)
        self.assertIn("FAILED", output)
        self.assertNotIn(PW, output)

    def test_connect_errors_hide_the_host_and_both_passwords(self):
        error = admin_sql.pymysql.MySQLError(2003, f"Can't connect to MySQL server on '10.0.0.1' (rootpw-xyz {PW})")
        rc, output, conn = run(apply=True, connect_error=error)
        self.assertEqual(rc, 1)
        for secret in ("10.0.0.1", "rootpw-xyz", PW):
            self.assertNotIn(secret, output)
        self.assertIn("***", output)
        self.assertEqual(conn.executed, [])

    def test_secret_username_must_match_the_sql(self):
        rc, output, conn = run(secret=json.dumps({"username": "someone", "password": PW}), apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("mcp_svc", output)
        self.assertEqual(conn.executed, [])

    def test_password_that_needs_quoting_is_refused(self):
        for bad in ("short1", "has'quote0123456789", "back\\slash0123456789", "sp ace0123456789abc"):
            with self.subTest(bad=bad):
                rc, output, conn = run(secret=json.dumps({"username": "mcp_svc", "password": bad}), apply=True)
                self.assertEqual(rc, 2)
                self.assertNotIn(bad, output)
                self.assertEqual(conn.executed, [])

    def test_malformed_secret_is_refused(self):
        rc, output, _ = run(secret="not json", apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("username", output)

    def test_missing_admin_credentials_is_refused(self):
        env = {k: v for k, v in ENV.items() if k != "DORIS_ADMIN_PASSWORD"}
        rc, output, conn = run(env=env, apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("DORIS_ADMIN_PASSWORD", output)
        self.assertEqual(conn.executed, [])


if __name__ == "__main__":
    unittest.main()
