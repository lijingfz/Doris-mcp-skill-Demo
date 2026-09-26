"""AgentCore Runtime entrypoint: Doris MCP (velodb-mcp-server @f235832 + AgentCore patches).

Runtime contract (protocol MCP): streamable HTTP on 0.0.0.0:8000/mcp, stateless.
Configuration: environment variables, see src/agentcore_ext/settings.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agentcore_ext.app import main  # noqa: E402

if __name__ == "__main__":
    main()
