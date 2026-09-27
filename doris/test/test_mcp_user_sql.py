"""Contract tests: doris/01_mcp_user.sql and 02_mcp_user_vpc.sql grant exactly what R-42 allows (offline).

    .venv/bin/python -m unittest discover -s doris/test -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

DORIS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DORIS_DIR))

import admin_sql  # noqa: E402

PW = "Abc123def456GHI789jkl012MNO345pq"


# Written with the placeholder: a literal password after IDENTIFIED BY trips scripts/check-secrets.sh.
EXPECTED = [
    "CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
    "ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
    "GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%'",
    "GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'%'",
]


class McpUserSql(unittest.TestCase):
    def test_statements_are_exactly_the_r42_account_setup(self):
        stmts = admin_sql.load_statements((DORIS_DIR / "01_mcp_user.sql").read_text(encoding="utf-8"))
        self.assertEqual(stmts, EXPECTED)
        self.assertEqual(admin_sql.render(stmts, {"MCP_SVC_PASSWORD": PW}),
                         [s.replace("${MCP_SVC_PASSWORD}", PW) for s in EXPECTED])


# P3 / T3.5: the same account from the VPC only (design §6.1); the '%' identity goes last.
EXPECTED_VPC = [
    "CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
    "ALTER USER 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}'",
    "GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%'",
    "GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'172.31.%'",
    "DROP USER IF EXISTS 'mcp_svc'@'%'",
]


class McpUserVpcSql(unittest.TestCase):
    def test_statements_move_the_account_to_the_vpc_range(self):
        stmts = admin_sql.load_statements((DORIS_DIR / "02_mcp_user_vpc.sql").read_text(encoding="utf-8"))
        self.assertEqual(stmts, EXPECTED_VPC)
        self.assertEqual(admin_sql.render(stmts, {"MCP_SVC_PASSWORD": PW}),
                         [s.replace("${MCP_SVC_PASSWORD}", PW) for s in EXPECTED_VPC])

    def test_same_grants_as_01_on_the_new_host(self):
        # 01 is the rollback (it re-creates the '%' identity), so the two must stay in step.
        self.assertEqual([s.replace("'172.31.%'", "'%'") for s in EXPECTED_VPC[:-1]], EXPECTED)


if __name__ == "__main__":
    unittest.main()
