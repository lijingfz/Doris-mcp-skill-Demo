"""Assemble the Doris MCP server for AgentCore Runtime (P-01)."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from agentcore_ext.settings import Settings, SettingsError, load_settings
from config.loader import AppConfig
from core.charset import CharsetMiddleware
from core.sensitive_mask import mask_sensitive
from server import create_server
from tools.profile import FeHttpTarget, register_profile_tools

logger = logging.getLogger("doris_new_mcp.agentcore")

MCP_PATH = "/mcp"
# Upstream's RequestLoggerMiddleware is deliberately not mounted: it logs request
# headers and bodies (SQL) to CloudWatch; tool calls are already in the audit log.
# SessionAffinityProxyMiddleware is for multi-node WebUI logins and does not apply.
HTTP_MIDDLEWARE = [Middleware(CharsetMiddleware)]
_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"


def build_server(settings: Settings, *, profile_transport: Any = None) -> FastMCP:
    """Upstream server in service mode + the two profile tools + GET /ping."""
    cfg = AppConfig(settings.config_dir)
    cfg.cluster.fe_host = settings.doris_host
    cfg.cluster.fe_mysql_port = settings.doris_port
    cfg.cluster.fe_http_port = settings.doris_http_port

    mcp = create_server(
        config_dir=settings.config_dir,
        config=cfg,
        service_credentials=(settings.doris_user, settings.doris_password),
        workspace_dir=settings.workspace_dir,
    )
    target = FeHttpTarget(
        base_url=f"http://{settings.doris_host}:{settings.doris_http_port}",
        user=settings.doris_user,
        password=settings.doris_password,
    )
    register_profile_tools(mcp, target, scope=settings.profile_scope, transport=profile_transport)

    @mcp.custom_route("/ping", methods=["GET"])
    async def ping(_: Request) -> JSONResponse:
        # AgentCore Runtime health check; must not touch Doris.
        return JSONResponse({"status": "Healthy", "time_of_last_update": int(time.time())})

    return mcp


def configure_logging() -> None:
    """Send the root and audit loggers to stderr, which AgentCore ships to CloudWatch.

    Upstream writes both only to files under the workspace dir; the audit logger
    does not propagate, so it needs its own handler. Safe to call repeatedly.
    """
    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    for name in ("", "doris_new_mcp.audit"):
        target = logging.getLogger(name)
        if any(getattr(h, "_agentcore_stderr", False) for h in target.handlers):
            continue
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        handler._agentcore_stderr = True  # type: ignore[attr-defined]
        target.addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def main() -> None:
    configure_logging()
    try:
        settings = load_settings()
    except SettingsError as e:
        logger.error("Invalid configuration: %s", e)
        sys.exit(2)
    try:
        mcp = build_server(settings)
    except Exception as e:  # noqa: BLE001 - one masked line and exit 2, like bad settings
        logger.error("Cannot build the MCP server: %s: %s", type(e).__name__, mask_sensitive(str(e)))
        sys.exit(2)
    logger.info(
        "Doris MCP for AgentCore: Doris %s:%d (http %d) as %s, profile scope %s, workspace %s",
        settings.doris_host, settings.doris_port, settings.doris_http_port,
        settings.doris_user, settings.profile_scope, settings.workspace_dir,
    )
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=settings.mcp_port,
        path=MCP_PATH,
        stateless_http=True,
        show_banner=False,
        middleware=HTTP_MIDDLEWARE,
    )
