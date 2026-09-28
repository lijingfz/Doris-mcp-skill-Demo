"""scripts/redact.py: secrets, URLs and IPv4 addresses out of error lines and the MCP SDK's log lines (P4 / T4.5)."""

import io
import logging
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redact  # noqa: E402

URL = "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/x/invocations?qualifier=DEFAULT"
IP_URL = "http://198.51.100.7:8000/mcp"  # TEST-NET-2
HOST = "198.51.100.7"


class Redact(unittest.TestCase):
    def test_a_secret_becomes_the_mask(self):
        self.assertEqual(redact.redact(f"POST {URL} failed", [URL]), "POST *** failed")

    def test_ipv4_addresses_become_ip(self):
        self.assertEqual(redact.redact("connect to 203.0.113.9:9030 refused", []), "connect to <ip>:9030 refused")

    def test_a_url_with_an_ipv4_host_is_masked_whole(self):
        self.assertEqual(redact.redact(f"POST {IP_URL} failed", [IP_URL]), "POST *** failed")

    def test_longer_secrets_are_replaced_first(self):
        # HOST is part of IP_URL: replacing it first would leave ":8000/mcp" behind.
        self.assertEqual(redact.redact(f"{IP_URL} via {HOST}", [HOST, IP_URL]), "*** via ***")

    def test_empty_secrets_are_ignored(self):
        self.assertEqual(redact.redact("nothing to hide", ["", None]), "nothing to hide")


class RedactSdkLogs(unittest.TestCase):
    def setUp(self):
        logger = logging.getLogger("mcp")
        self.enterContext(mock.patch.object(logger, "handlers", []))
        self.enterContext(mock.patch.object(logger, "propagate", True))
        self.stream = io.StringIO()

    def test_sdk_log_lines_are_redacted(self):
        redact.redact_sdk_logs([URL], self.stream)
        logging.getLogger("mcp.client.streamable_http").warning("Session termination failed: DELETE %s", URL)
        self.assertEqual(self.stream.getvalue(), "WARNING mcp.client.streamable_http: Session termination failed: "
                                                 "DELETE ***\n")

    def test_sdk_tracebacks_are_redacted(self):
        redact.redact_sdk_logs([URL], self.stream)
        try:
            raise RuntimeError(f"Client error '403 Forbidden' for url '{URL}' from 203.0.113.9")
        except RuntimeError:
            logging.getLogger("mcp.client.streamable_http").exception("Error in post_writer")
        text = self.stream.getvalue()
        self.assertIn("Traceback", text)
        self.assertIn("RuntimeError: Client error '403 Forbidden' for url '***' from <ip>", text)
        self.assertNotIn(URL, text)
        self.assertNotIn("203.0.113.9", text)

    def test_one_handler_and_nothing_reaches_the_root_logger(self):
        redact.redact_sdk_logs([URL], io.StringIO())
        handler = redact.redact_sdk_logs([URL], self.stream)
        logger = logging.getLogger("mcp")
        self.assertEqual(logger.handlers, [handler])
        self.assertFalse(logger.propagate)
        with self.assertNoLogs(level="DEBUG"):  # assertNoLogs() watches the root logger
            logging.getLogger("mcp.client").error("POST %s", URL)
        self.assertEqual(self.stream.getvalue(), "ERROR mcp.client: POST ***\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
