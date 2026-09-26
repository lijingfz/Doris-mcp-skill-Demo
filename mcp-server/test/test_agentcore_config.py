"""P-02: ClusterConfig.fe_http_port (Doris FE HTTP port used by the profile tools)."""

import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.loader import AppConfig  # noqa: E402


class TestFeHttpPort(unittest.TestCase):
    def _config(self, toml: str) -> AppConfig:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "mcp-server.toml").write_text(toml, encoding="utf-8")
            return AppConfig(tmp)

    def test_default_is_8030(self):
        self.assertEqual(self._config("[server]\n").cluster.fe_http_port, 8030)

    def test_explicit_port(self):
        cfg = self._config("[server]\nfe_http_port = 18030\n")
        self.assertEqual(cfg.cluster.fe_http_port, 18030)

    def test_string_port_is_coerced_to_int(self):
        cfg = self._config('[server]\nfe_http_port = "8031"\n')
        self.assertEqual(cfg.cluster.fe_http_port, 8031)

    def test_no_config_file_uses_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(AppConfig(tmp).cluster.fe_http_port, 8030)


if __name__ == "__main__":
    unittest.main(verbosity=2)
