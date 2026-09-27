"""SigV4-signed MCP client for an AgentCore Runtime invoke URL (inbound auth AWS_IAM).

    from agentcore_client import sigv4_client
    async with sigv4_client(runtime_url) as client:
        await client.list_tools()

Credentials come from the default botocore chain (here: the AWS_* environment variables) and are
re-read before each request, so refreshed session credentials are picked up. The region comes from
the URL unless given: this dev box sets AWS_DEFAULT_REGION=us-west-2, the Runtime is in us-east-1.
One Client is one MCP session (Mcp-Session-Id), i.e. one Runtime microVM; the Gateway opens a new
session for every tool call.
"""

from __future__ import annotations

import re
from typing import Generator

import botocore.session
import httpx
from botocore.auth import SigV4Auth as _BotoSigV4Auth
from botocore.awsrequest import AWSRequest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

SERVICE = "bedrock-agentcore"
# botocore already skips hop-by-hop headers and user-agent; accept-encoding is set by httpx and
# may be rewritten on the way, so it is not signed either.
_UNSIGNED = frozenset({"accept-encoding"})
_REGION_RE = re.compile(r"^https://bedrock-agentcore\.([a-z0-9-]+)\.amazonaws\.com/")


def region_from_url(url: str) -> str | None:
    m = _REGION_RE.match(url)
    return m.group(1) if m else None


class SigV4Auth(httpx.Auth):
    """httpx auth that signs every request (body included) for bedrock-agentcore."""

    requires_request_body = True

    def __init__(self, region: str, credentials=None, service: str = SERVICE):
        self._region, self._service = region, service
        self._credentials = credentials or botocore.session.get_session().get_credentials()
        if self._credentials is None:
            raise RuntimeError("no AWS credentials found (set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)")

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _UNSIGNED}
        aws = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=headers)
        _BotoSigV4Auth(self._credentials.get_frozen_credentials(), self._service, self._region).add_auth(aws)
        for name in ("Authorization", "X-Amz-Date", "X-Amz-Security-Token"):
            if name in aws.headers:
                request.headers[name] = aws.headers[name]
        yield request


def sigv4_client(url: str, region: str | None = None, timeout: float = 90.0) -> Client:
    region = region or region_from_url(url)
    if not region:
        raise ValueError(f"cannot tell the region from {url!r}; pass --region")
    return Client(StreamableHttpTransport(url, auth=SigV4Auth(region)), timeout=timeout)
