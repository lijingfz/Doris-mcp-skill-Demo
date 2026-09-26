"""Assemble the Doris MCP server for AgentCore Runtime (P-01)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from agentcore_ext.settings import Settings
from config.loader import AppConfig
from server import create_server
from tools.profile import FeHttpTarget, register_profile_tools


def build_server(settings: Settings, *, profile_transport: Any = None) -> FastMCP:
    """Upstream server in service mode + the two profile tools."""
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
    return mcp
