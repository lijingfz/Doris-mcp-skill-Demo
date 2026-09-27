-- P3 / T3.5 — move the doris-mcp service account to the VPC range (design §6.1, R-42, P2 review carry-forward).
-- Run as root through doris/apply-admin-sql.sh (dry-run by default; APPLY=1 only after the GATE).
-- ${MCP_SVC_PASSWORD} is filled in memory from Secrets Manager doris-mcp/mcp_svc; never write it here.
-- The Runtime ENIs are in 172.31.0.0/16. The new identity gets the same password and grants as 01 first;
-- only then is 'mcp_svc'@'%' dropped, so the account is never without a working identity.
-- Afterwards mcp_svc cannot log in from outside 172.31.%: that includes the dev box (expected, 1045).
-- Re-run safe (IF NOT EXISTS / IF EXISTS). Rollback: re-run doris/01_mcp_user.sql (re-creates '%').
CREATE USER IF NOT EXISTS 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'172.31.%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'172.31.%';
GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'172.31.%';
DROP USER IF EXISTS 'mcp_svc'@'%';
