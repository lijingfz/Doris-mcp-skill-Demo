"""P0 spike: minimal MCP server proving AgentCore Runtime (VPC mode) -> Doris reachability.

Exposes one read-only tool, ``net_check``: it opens a TCP connection to the
Doris FE MySQL port and parses the protocol greeting, then sends an HTTP GET
to the FE HTTP port. No credentials are used or returned.
"""

import asyncio
import os
import time

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

DORIS_HOST = os.environ.get("DORIS_HOST", "127.0.0.1")
DORIS_PORT = int(os.environ.get("DORIS_PORT", "9030"))
DORIS_HTTP_PORT = int(os.environ.get("DORIS_HTTP_PORT", "8030"))
MCP_PORT = int(os.environ.get("MCP_PORT", "8000"))
TIMEOUT_S = 5.0

mcp = FastMCP(name="doris-mcp-spike")


def _ms(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


async def mysql_greeting(host: str, port: int, timeout: float = TIMEOUT_S) -> dict:
    """Connect to a MySQL-protocol port and return the server version from the v10 handshake."""
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        try:
            header = await asyncio.wait_for(reader.readexactly(4), timeout)
            payload = await asyncio.wait_for(
                reader.readexactly(int.from_bytes(header[:3], "little")), timeout
            )
        finally:
            writer.close()
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
        return {"ok": False, "ms": _ms(start), "error": f"{type(e).__name__}: {e}"}
    if not payload or payload[0] != 10:
        return {"ok": False, "ms": _ms(start), "error": f"unexpected first byte 0x{payload[:1].hex()}"}
    end = payload.find(b"\x00", 1)
    banner = payload[1:end if end > 0 else None].decode("ascii", "replace")
    return {"ok": True, "ms": _ms(start), "banner": banner}


async def http_status(url: str, timeout: float = TIMEOUT_S, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """GET a URL and return its status code; any HTTP response means the port is reachable."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        return {"ok": False, "ms": _ms(start), "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "ms": _ms(start), "status": resp.status_code}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
async def net_check() -> dict:
    """Check network reachability from this runtime to the Doris FE (MySQL port and HTTP port). Uses no credentials."""
    mysql, http = await asyncio.gather(
        mysql_greeting(DORIS_HOST, DORIS_PORT),
        http_status(f"http://{DORIS_HOST}:{DORIS_HTTP_PORT}/"),
    )
    return {
        "target": DORIS_HOST,
        "mysql": {"port": DORIS_PORT, **mysql},
        "http": {"port": DORIS_HTTP_PORT, **http},
    }


@mcp.custom_route("/ping", methods=["GET"])
async def ping(_: Request) -> JSONResponse:
    return JSONResponse({"status": "Healthy"})


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=MCP_PORT,
        path="/mcp",
        stateless_http=True,
        show_banner=False,
    )
