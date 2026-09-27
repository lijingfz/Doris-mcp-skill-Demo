"""Runtime settings from environment variables (design §5.4).

DORIS_HOST (required), DORIS_PORT=9030, DORIS_HTTP_PORT=8030
DORIS_SECRET_ID            Secrets Manager secret {"username": ..., "password": ...}; wins over
DORIS_USER / DORIS_PASSWORD  (local runs only)
PROFILE_SCOPE=all|self     self: profile tools only ever see the service account's own profiles
DORIS_MCP_WORKSPACE_DIR    default $TMPDIR/doris-mcp-workspace (the code dir is read-only on AgentCore)
DORIS_MCP_CONFIG_DIR       default <mcp-server>/config
MCP_PORT=8000
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class SettingsError(RuntimeError):
    """Invalid or missing configuration; messages never contain secret values."""


@dataclass(frozen=True)
class Settings:
    doris_host: str
    doris_port: int
    doris_http_port: int
    doris_user: str
    doris_password: str = field(repr=False)
    profile_scope: str = "all"
    workspace_dir: str = ""
    config_dir: str = str(_DEFAULT_CONFIG_DIR)
    mcp_port: int = 8000


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name) or str(default)
    try:
        value = int(raw)
    except ValueError:
        raise SettingsError(f"{name} must be an integer, got {raw!r}") from None
    if not 0 < value < 65536:
        raise SettingsError(f"{name} out of range: {value}")
    return value


def _secrets_client(env: Mapping[str, str]) -> Any:
    import boto3
    from botocore.config import Config

    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    # Fail fast when the secretsmanager VPC endpoint is missing instead of hanging the cold start.
    config = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"})
    return boto3.client("secretsmanager", region_name=region, config=config)


def _credentials_from_secret(secret_id: str, client: Any) -> tuple[str, str]:
    try:
        raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    except Exception as e:  # noqa: BLE001 - only the type: the message may carry request details
        raise SettingsError(f"cannot read secret {secret_id}: {type(e).__name__}") from None
    try:
        doc = json.loads(raw)
        user, password = doc["username"], doc["password"]
    except (ValueError, TypeError, KeyError):
        raise SettingsError(f"secret {secret_id} must be JSON with 'username' and 'password'") from None
    if not isinstance(user, str) or not isinstance(password, str) or not user or not password:
        raise SettingsError(f"secret {secret_id} has an empty or non-string username/password")
    return user, password


def load_settings(env: Mapping[str, str] | None = None, secrets_client: Any = None) -> Settings:
    env = os.environ if env is None else env
    host = (env.get("DORIS_HOST") or "").strip()
    if not host:
        raise SettingsError("DORIS_HOST is required")

    secret_id = (env.get("DORIS_SECRET_ID") or "").strip()
    if secret_id:
        user, password = _credentials_from_secret(secret_id, secrets_client or _secrets_client(env))
    else:
        user, password = env.get("DORIS_USER") or "", env.get("DORIS_PASSWORD")
        if not user or password is None:
            raise SettingsError("set DORIS_SECRET_ID, or DORIS_USER and DORIS_PASSWORD")

    scope = env.get("PROFILE_SCOPE") or "all"
    if scope not in ("all", "self"):
        raise SettingsError(f"PROFILE_SCOPE must be 'all' or 'self', got {scope!r}")

    return Settings(
        doris_host=host,
        doris_port=_int(env, "DORIS_PORT", 9030),
        doris_http_port=_int(env, "DORIS_HTTP_PORT", 8030),
        doris_user=user,
        doris_password=password,
        profile_scope=scope,
        workspace_dir=env.get("DORIS_MCP_WORKSPACE_DIR")
        or os.path.join(tempfile.gettempdir(), "doris-mcp-workspace"),
        config_dir=env.get("DORIS_MCP_CONFIG_DIR") or str(_DEFAULT_CONFIG_DIR),
        mcp_port=_int(env, "MCP_PORT", 8000),
    )
