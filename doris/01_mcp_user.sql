-- P2 / T2.2 — Doris service account for the doris-mcp Runtime (design §6.1, R-42).
-- Run as root through doris/apply-admin-sql.sh (dry-run by default; APPLY=1 only after the GATE).
-- ${MCP_SVC_PASSWORD} is filled in memory from Secrets Manager doris-mcp/mcp_svc; never write it here.
-- Re-run safe: CREATE ... IF NOT EXISTS, ALTER USER converges the password to the secret, GRANT is additive.
-- Host '%' for now (D6: P2 connects from the dev box); P3 T3.5 narrows it to '172.31.%'.
-- No ADMIN / LOAD / ALTER / DROP. CREATE on system_mcp only lets upstream's CREATE ... IF NOT EXISTS pass.
CREATE USER IF NOT EXISTS 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
ALTER USER 'mcp_svc'@'%' IDENTIFIED BY '${MCP_SVC_PASSWORD}';
GRANT SELECT_PRIV ON internal.ecom.* TO 'mcp_svc'@'%';
GRANT SELECT_PRIV, CREATE_PRIV ON internal.system_mcp.* TO 'mcp_svc'@'%';
