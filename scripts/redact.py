"""Mask secrets and IPv4 addresses in error lines and in the MCP SDK's own log lines (P4 / T4.5).

    import redact
    redact.redact_sdk_logs([url, token])          # mcp.* log records -> stderr, masked
    print(redact.redact(str(e), [url, token]))    # literal secrets -> ***, then IPv4 -> <ip>

The MCP SDK logs transport failures itself (e.g. "Session termination failed", or an httpx error
whose message carries the full URL); the "mcp" logger has no handler of its own, so without this
those records reach stderr unmasked through logging.lastResort.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, TextIO

MASK = "***"
IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def redact(text: str, secrets: Iterable[str | None]) -> str:
    """Literal secrets -> ***, longest first (a host inside the URL), then every IPv4 address -> <ip>."""
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, MASK)
    return IPV4_RE.sub("<ip>", text)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str | None]):
        super().__init__("%(levelname)s %(name)s: %(message)s")
        self._secrets = list(secrets)

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self._secrets)  # the traceback too


def redact_sdk_logs(secrets: Iterable[str | None], stream: TextIO | None = None) -> logging.Handler:
    """Send the "mcp" logger's records to stream (default: stderr) through redact(), and nowhere else."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_RedactingFormatter(secrets))
    logger = logging.getLogger("mcp")
    logger.handlers[:] = [handler]
    logger.propagate = False
    return handler
