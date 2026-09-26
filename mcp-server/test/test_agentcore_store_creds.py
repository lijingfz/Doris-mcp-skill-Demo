"""P-03: process-wide service credentials as a fallback for the store layer.

Request credentials (set by CredentialVerifier) must always win; with neither
set, the upstream "no credentials" RuntimeError must be preserved.
"""

import asyncio
import contextvars
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import store.store as st  # noqa: E402
from store.bootstrap import pre_validate_physical  # noqa: E402


def _fresh(fn, *args):
    """Run fn in an empty context so request credentials from other tests never leak in."""
    return contextvars.Context().run(fn, *args)


class TestEffectiveCredentials(unittest.TestCase):
    def tearDown(self):
        st.clear_service_credentials()

    def test_none_when_nothing_set(self):
        self.assertIsNone(_fresh(st.get_effective_credentials))

    def test_service_credentials_used_without_request_credentials(self):
        st.set_service_credentials("mcp_svc", "svc-pw")
        self.assertEqual(_fresh(st.get_effective_credentials), ("mcp_svc", "svc-pw"))

    def test_request_credentials_win_over_service_credentials(self):
        st.set_service_credentials("mcp_svc", "svc-pw")

        def run():
            st.set_request_credentials("alice", "alice-pw")
            return st.get_effective_credentials()

        self.assertEqual(_fresh(run), ("alice", "alice-pw"))

    def test_clear_restores_upstream_behavior(self):
        st.set_service_credentials("mcp_svc", "svc-pw")
        st.clear_service_credentials()
        self.assertIsNone(_fresh(st.get_effective_credentials))

    def test_service_credentials_visible_in_worker_threads(self):
        st.set_service_credentials("mcp_svc", "svc-pw")

        async def run():
            return await asyncio.to_thread(st.get_effective_credentials)

        self.assertEqual(_fresh(asyncio.run, run()), ("mcp_svc", "svc-pw"))


class TestGetConn(unittest.TestCase):
    def tearDown(self):
        st.clear_service_credentials()

    def test_get_conn_uses_service_credentials(self):
        st.set_service_credentials("mcp_svc", "svc-pw")
        with patch("store.store.pymysql.connect") as connect:
            _fresh(st._get_conn)
        kwargs = connect.call_args.kwargs
        self.assertEqual((kwargs["user"], kwargs["password"]), ("mcp_svc", "svc-pw"))

    def test_get_conn_without_any_credentials_still_raises(self):
        with patch("store.store.pymysql.connect") as connect:
            with self.assertRaises(RuntimeError):
                _fresh(st._get_conn)
        connect.assert_not_called()


class TestPreValidatePhysical(unittest.TestCase):
    def tearDown(self):
        st.clear_service_credentials()

    def test_no_credentials_message_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, msg = _fresh(pre_validate_physical, Path(tmp))
        self.assertFalse(ok)
        self.assertIn("No Doris credentials available", msg)

    def test_service_credentials_reach_pymysql(self):
        st.set_service_credentials("mcp_svc", "svc-pw")
        with tempfile.TemporaryDirectory() as tmp:
            with patch("pymysql.connect") as connect:
                _fresh(pre_validate_physical, Path(tmp))
        kwargs = connect.call_args.kwargs
        self.assertEqual((kwargs["user"], kwargs["password"]), ("mcp_svc", "svc-pw"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
