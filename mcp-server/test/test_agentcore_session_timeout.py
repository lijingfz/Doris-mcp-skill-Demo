"""P-09: [query] session_wait_timeout_seconds -> SET wait_timeout on every pool connection.

Each Gateway call runs in a fresh Runtime microVM; pool connections left open when a microVM is torn
down stay on Doris until its wait_timeout (default 28800 s) unless the session sets a shorter one.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.loader import AppConfig  # noqa: E402
from core.connection import ConnectionPool  # noqa: E402

_SHIPPED_CONFIG = Path(__file__).resolve().parent.parent / "config"


def _config(toml: str) -> AppConfig:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "mcp-server.toml").write_text(toml, encoding="utf-8")
        return AppConfig(tmp)


class TestSessionWaitTimeoutConfig(unittest.TestCase):
    def test_default_is_none(self):
        self.assertIsNone(_config("[query]\n").cluster.session_wait_timeout)

    def test_explicit_value(self):
        cfg = _config("[query]\nsession_wait_timeout_seconds = 600\n")
        self.assertEqual(cfg.cluster.session_wait_timeout, 600)

    def test_string_value_is_coerced_to_int(self):
        cfg = _config('[query]\nsession_wait_timeout_seconds = "900"\n')
        self.assertEqual(cfg.cluster.session_wait_timeout, 900)

    def test_shipped_config_outlives_the_pool_recycle(self):
        # A pooled connection idle for pool_idle_timeout_seconds is recycled by aiomysql; Doris must not
        # drop it first, or the next query on it fails.
        cluster = AppConfig(_SHIPPED_CONFIG).cluster
        self.assertEqual(cluster.session_wait_timeout, 600)
        self.assertGreater(cluster.session_wait_timeout, cluster.pool_idle_timeout)


class TestPoolInitCommand(unittest.TestCase):
    def _create_pool_kwargs(self, toml: str) -> dict:
        pool = ConnectionPool(_config(toml).cluster, "mcp_svc", "pw", host="10.0.0.5")
        create = mock.AsyncMock(return_value=SimpleNamespace(closed=False))
        with mock.patch("core.connection.aiomysql.create_pool", create):
            asyncio.run(pool._ensure_pool())
        create.assert_awaited_once()
        return create.await_args.kwargs

    def test_pool_sets_the_session_wait_timeout(self):
        kwargs = self._create_pool_kwargs("[query]\nsession_wait_timeout_seconds = 600\n")
        self.assertEqual(kwargs["init_command"], "SET wait_timeout = 600")
        self.assertTrue(kwargs["autocommit"])

    def test_no_init_command_without_the_setting(self):
        kwargs = self._create_pool_kwargs("[query]\n")
        self.assertNotIn("init_command", kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
