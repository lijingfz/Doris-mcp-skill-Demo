import asyncio
import json
import unittest
from unittest import mock

import httpx
from fastmcp import Client
from starlette.testclient import TestClient

import mcp_server


def _greeting(first_byte: bytes = b"\x0a", version: bytes = b"5.7.99") -> bytes:
    payload = first_byte + version + b"\x00" + b"\x00" * 20
    return len(payload).to_bytes(3, "little") + b"\x00" + payload


class FakeMySQL:
    """Local TCP server that sends one packet and closes."""

    def __init__(self, packet: bytes):
        self.packet = packet

    async def __aenter__(self):
        async def handle(reader, writer):
            writer.write(self.packet)
            await writer.drain()
            writer.close()

        self.server = await asyncio.start_server(handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()


class MySQLGreetingTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_server_version(self):
        async with FakeMySQL(_greeting()) as port:
            result = await mcp_server.mysql_greeting("127.0.0.1", port, timeout=2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["banner"], "5.7.99")

    async def test_error_packet_is_not_ok(self):
        async with FakeMySQL(_greeting(first_byte=b"\xff", version=b"denied")) as port:
            result = await mcp_server.mysql_greeting("127.0.0.1", port, timeout=2)
        self.assertFalse(result["ok"])
        self.assertIn("0xff", result["error"])

    async def test_closed_port_is_not_ok(self):
        async with FakeMySQL(b"") as port:
            pass  # server closed -> port refuses connections
        result = await mcp_server.mysql_greeting("127.0.0.1", port, timeout=2)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


class HttpStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_any_status_is_reachable(self):
        transport = httpx.MockTransport(lambda req: httpx.Response(401))
        result = await mcp_server.http_status("http://doris:8030/", transport=transport)
        self.assertEqual(result, {"ok": True, "ms": result["ms"], "status": 401})

    async def test_connect_error_is_not_ok(self):
        def boom(req):
            raise httpx.ConnectError("refused", request=req)

        result = await mcp_server.http_status("http://doris:8030/", transport=httpx.MockTransport(boom))
        self.assertFalse(result["ok"])
        self.assertIn("ConnectError", result["error"])


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_net_check_tool_is_listed_read_only(self):
        async with Client(mcp_server.mcp) as client:
            tools = {t.name: t for t in await client.list_tools()}
        self.assertEqual(set(tools), {"net_check"})
        self.assertTrue(tools["net_check"].annotations.readOnlyHint)

    async def test_net_check_reports_both_ports(self):
        async with FakeMySQL(_greeting()) as port:
            with mock.patch.multiple(mcp_server, DORIS_HOST="127.0.0.1", DORIS_PORT=port, DORIS_HTTP_PORT=1):
                async with Client(mcp_server.mcp) as client:
                    result = await client.call_tool("net_check", {})
        data = json.loads(result.content[0].text)
        self.assertTrue(data["mysql"]["ok"])
        self.assertFalse(data["http"]["ok"])  # nothing listens on port 1

    def test_ping_route(self):
        app = mcp_server.mcp.http_app(path="/mcp", stateless_http=True)
        with TestClient(app) as http:
            resp = http.get("/ping")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "Healthy"})


if __name__ == "__main__":
    unittest.main()
