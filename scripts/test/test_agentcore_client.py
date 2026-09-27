"""scripts/agentcore_client.py: SigV4 (bedrock-agentcore) auth for a Runtime's MCP invoke URL (P3 / T3.3).

The signature is checked the way the service checks it: recomputed from the request as it arrives,
over the headers the request says it signed.
"""

import datetime as dt
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import httpx
from botocore.auth import SigV4Auth as BotoSigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agentcore_client  # noqa: E402
from agentcore_client import SigV4Auth, region_from_url  # noqa: E402

URL = ("https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
       "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A111122223333%3Aruntime%2Fdorismcp_dorismcp-AbCdEf1234"
       "/invocations?qualifier=DEFAULT")
CREDS = Credentials("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "session-token-example")
NOW = dt.datetime(2026, 9, 27, 8, 0, 0)
BODY = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'


def _parts(request: httpx.Request) -> tuple[list[str], str]:
    auth = request.headers["authorization"]
    return (re.search(r"SignedHeaders=([^,]+)", auth).group(1).split(";"),
            re.search(r"Signature=([0-9a-f]{64})$", auth).group(1))


def _service_signature(request: httpx.Request, body: bytes | None = None) -> str:
    """What the service computes from the received method, URL, signed headers and body."""
    signed, _ = _parts(request)
    aws = AWSRequest(method=request.method, url=str(request.url),
                     data=request.content if body is None else body,
                     headers={h: request.headers[h] for h in signed})
    aws.context["timestamp"] = request.headers["x-amz-date"]
    signer = BotoSigV4Auth(CREDS.get_frozen_credentials(), "bedrock-agentcore", "us-east-1")
    return signer.signature(signer.string_to_sign(aws, signer.canonical_request(aws)), aws)


class TestSigV4Auth(unittest.IsolatedAsyncioTestCase):
    async def _send(self, headers: dict | None = None, credentials=CREDS) -> httpx.Request:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        auth = SigV4Auth("us-east-1", credentials=credentials)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), auth=auth) as client:
            with mock.patch("botocore.auth.get_current_datetime", return_value=NOW):
                await client.post(URL, content=BODY, headers={"content-type": "application/json",
                                                               "accept": "application/json, text/event-stream",
                                                               **(headers or {})})
        return seen[0]

    async def test_credential_scope_is_bedrock_agentcore_in_the_region(self):
        request = await self._send()
        self.assertTrue(request.headers["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20260927/us-east-1/bedrock-agentcore/aws4_request, "))
        self.assertEqual(request.headers["x-amz-date"], "20260927T080000Z")

    async def test_signature_verifies_on_the_received_request(self):
        request = await self._send()
        self.assertEqual(_parts(request)[1], _service_signature(request))

    async def test_body_is_signed(self):
        request = await self._send()
        self.assertNotEqual(_parts(request)[1], _service_signature(request, body=BODY.replace(b"list", b"call")))

    async def test_session_token_is_sent_and_signed(self):
        request = await self._send()
        self.assertEqual(request.headers["x-amz-security-token"], "session-token-example")
        self.assertIn("x-amz-security-token", _parts(request)[0])

    async def test_mcp_session_id_is_signed(self):
        # The Runtime routes a session to its microVM by this header; an unsigned one could be swapped.
        request = await self._send({"mcp-session-id": "0f3c"})
        self.assertIn("mcp-session-id", _parts(request)[0])
        self.assertEqual(_parts(request)[1], _service_signature(request))

    async def test_headers_a_proxy_may_rewrite_are_not_signed(self):
        signed, _ = _parts(await self._send())
        self.assertIn("host", signed)
        self.assertIn("content-type", signed)
        for header in ("accept-encoding", "connection", "user-agent"):
            self.assertNotIn(header, signed)

    def test_missing_credentials_fail_at_construction(self):
        session = mock.Mock()
        session.get_credentials.return_value = None
        with mock.patch.object(agentcore_client.botocore.session, "get_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "no AWS credentials"):
                SigV4Auth("us-east-1")


class TestRegionFromUrl(unittest.TestCase):
    def test_runtime_invoke_url(self):
        self.assertEqual(region_from_url(URL), "us-east-1")

    def test_other_region(self):
        self.assertEqual(region_from_url(URL.replace("us-east-1.amazonaws", "eu-west-1.amazonaws")), "eu-west-1")

    def test_not_an_agentcore_url(self):
        self.assertIsNone(region_from_url("http://127.0.0.1:8000/mcp"))


class TestSigV4Client(unittest.TestCase):
    def test_region_defaults_to_the_url_not_aws_default_region(self):
        # This dev box sets AWS_DEFAULT_REGION=us-west-2; the Runtime is in us-east-1.
        with mock.patch.dict("os.environ", {"AWS_DEFAULT_REGION": "us-west-2"}), \
                mock.patch.object(agentcore_client, "SigV4Auth") as auth:
            agentcore_client.sigv4_client(URL)
        auth.assert_called_once_with("us-east-1")

    def test_explicit_region_wins(self):
        with mock.patch.object(agentcore_client, "SigV4Auth") as auth:
            agentcore_client.sigv4_client(URL, region="eu-west-1")
        auth.assert_called_once_with("eu-west-1")

    def test_region_is_required_for_a_non_agentcore_url(self):
        with self.assertRaisesRegex(ValueError, "--region"):
            agentcore_client.sigv4_client("http://127.0.0.1:8000/mcp")


if __name__ == "__main__":
    unittest.main(verbosity=2)
