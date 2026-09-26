# P1 本地改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务执行本计划。步骤用复选框（`- [ ]`）跟踪。
> **断线恢复：** 先按仓库根目录 `CLAUDE.md` 的恢复协议执行，再从 `progress.md`「当前状态」里写的任务/步骤继续。本计划里所有命令都在仓库根目录 `/home/ubuntu/AI-code/Doris-mcp-skill-Demo` 下运行，除非步骤里明确写了 `cd`。
> **代码来源：** 本计划中的全部代码和测试已在 spec 阶段于临时目录完成 TDD，并用 `demo_ro` 对真实 Doris 跑通了 T1.8 的只读 E2E（77 个新测试 + upstream 离线测试全部通过；flow 6/6）。执行时照抄即可；如果某一步的实际输出与「期望」不一致，先停下来查原因，不要改测试去迁就实现。

**Goal:** 把 upstream `velodb-mcp-server` @ `f235832` vendoring 到 `mcp-server/`，叠加 8 处 AgentCore 补丁（P-01–P-08），在本机用只读账号 `demo_ro` 连 Doris 公网 IP 跑通 12 个工具、profile 流程和 3 种错误情况；产物就是 P3 要部署的 CodeZip 目录。

**Architecture:** upstream 代码第一次提交保持原样，之后每处补丁单独一个 commit（升级时可 rebase）。对 upstream 的改动只有 3 个文件、全部向后兼容（P-02/P-03/P-04，没设服务凭证时行为与 upstream 完全一致）；AgentCore 相关逻辑都放在新文件里：`src/agentcore_ext/`（env/secret 配置、组装 server、`/ping`、stderr 日志、`main`）、`src/tools/profile.py`（两个 profile 工具）、`mcp_server.py`（入口）、`config/mcp-server.toml`（运行参数）。MCP 层不做鉴权（交给 Runtime IAM / Gateway JWT），所有 SQL 和 FE HTTP 请求都用同一个 Doris 服务账号。

**Tech Stack:** Python 3.12 · FastMCP 3.4.4 / mcp 1.28.1 / Starlette 1.3.1 / uvicorn 0.51.0 · httpx 0.28.1（FE HTTP，测试用 `httpx.MockTransport`）· pymysql / aiomysql · boto3（Secrets Manager）· unittest（与 upstream 一致，不引入 pytest）· uv

**Spec:** `specs/doris-mcp-quick/requirements.md`（R-12、R-20–R-25、R-30–R-35、R-43）、`specs/doris-mcp-quick/design.md`（§4.1、§4.6、§5、§11 P1 行、§13）

## Global Constraints

- upstream 锁定 `https://github.com/velodb/velodb-mcp-server` commit `f235832`（tag `velodb-mcp-server-0.3.0`）；vendoring 的路径只有 `src test LICENSE.txt NOTICE mcp-server.toml requirements.txt`。
- 对 upstream 文件的修改**只允许** P-02（`src/config/loader.py`）、P-03（`src/store/store.py`、`src/store/bootstrap.py`）、P-04（`src/server.py`）；upstream 自己的测试一个都不改。
- 依赖版本锁定为 upstream `uv.lock` 的版本（见 T1.1 的 `pyproject.toml`），额外只加 `boto3==1.43.103`；不新增其他依赖。
- 工具数恰好 **12**：upstream 10 个 + `list_recent_queries` + `get_query_profile`；工具名不带 `_tool` 后缀；每个 inputSchema 通过 `jsonschema.Draft7Validator.check_schema`。
- 运行契约：`streamable-http`、`0.0.0.0:8000/mcp`、`stateless_http=True`、`GET /ping` 不访问 Doris；SQL 超时 50 s、FE HTTP 超时 15 s、Secrets Manager 连接 5 s / 读取 10 s。
- 密码不出现在仓库、命令行参数、日志、工具返回值、异常消息和对话输出里。Doris 凭证只从 `/home/ubuntu/AI-code/Doris-test/credentials.env` 在**子 shell** 里 `source`（该文件没有 `export` 行，source 后变量不会自动传给子进程），只 export 需要的变量；**永远不要 echo 或 cat 这个文件**。
- P1 只用 `demo_ro`（只读），只执行 SELECT；MCP 不执行任何 DDL/DML。T1.8 会故意用错误密码登录一次，不会更多。
- 本地跑的 server 用端口停止：`ss -ltnp | grep ':PORT '` 找到 pid 再 `kill`。**不要用 `pkill -f <pattern>`**：pattern 会匹配到执行它的那个 shell 自身，把当前命令一起杀掉。
- 代码、注释、工具描述用英文（与 upstream 一致）；计划和 progress 用中文。
- 每个任务结束：勾选 `tasks.md` → 更新 `progress.md`（「当前状态」+ 追加日志）→ `bash scripts/check-secrets.sh` → commit（message 结尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。不 push。

## Review Focus

1. **Doris 用 HTTP 200 返回错误**：密码错误是 body `code:401`，别人的 profile 是 `code:0, data:{}`，非法 id 是 JSON `code:500`，找不到的 id 是纯文本 `query id <id> not found`。只看 HTTP 状态码会把错误当成功、把错误文本当成 profile。→ T1.5 的 `test_body_code_401_is_unauthenticated`、`test_api_text_json_error_is_not_found`、`test_api_text_must_start_with_a_section_to_count_as_a_profile`；T1.8 用真实 Doris 复核。
2. **query_id 路径注入**：`query_id` 会拼进 FE URL 路径，`../../api/x` 这类输入必须在发请求之前就被拒绝。→ T1.5 的 `test_invalid_query_ids_make_no_request`（断言零请求）；T1.6 经完整 server 调用再测一次；T1.8 flow 对真实 server 测。
3. **密码泄漏**：服务账号密码可能经由错误消息、工具返回值、`repr`、启动日志、HTTP 请求日志泄漏。→ T1.4 `test_service_password_not_in_error_payload`；T1.5 `test_repr_hides_password` 和错误路径的 `assertNotIn`；T1.6 每个 `SettingsError` 都断言不含密码（包括 boto3 异常消息里带密码的情况）；T1.7 配置错误退出时日志不含密码；T1.8 对所有日志文件 grep 真实密码，命中数必须为 0。upstream 的 `RequestLoggerMiddleware` 会记录请求 body（SQL）和 header，入口**不挂载**它。
4. **Quick 固定 60 s 超时**：任何一个环节卡住都会让 Quick 报 424。→ T1.6 `TestRuntimeConfig` 锁定 `query_timeout=50`；T1.5 `FeHttpTarget.timeout=15.0` + `test_timeout_and_connect_errors`（超时返回 `QUERY_TIMEOUT` 而不是挂起）；T1.6 的 boto3 客户端超时 5/10 s、重试 2 次。
5. **冷启动时配置缺失或错误**：secret 读不到、env 缺失、端口不是数字时，应当立刻以退出码 2 退出并给出清晰原因（不含密码）；Doris 不可达或密码错误时，server 照常启动，工具返回结构化错误 JSON，不抛异常、不断开 MCP 连接。→ T1.6 `TestSettingsErrors`；T1.7 `test_bad_settings_exit_2_with_a_clear_message`；T1.8 用错误密码起第二个实例，逐个核对错误码。

---

## 文件地图

| 文件 | 状态 | 任务 | 作用 |
|---|---|---|---|
| `mcp-server/{src,test,LICENSE.txt,NOTICE,mcp-server.toml,requirements.txt}` | vendoring | T1.1 | upstream @f235832 原样；`requirements.txt` 是 upstream `test/test_deps.py` 必需的 |
| `mcp-server/UPSTREAM.md` | 新建 | T1.1 | upstream 来源、锁定 commit、补丁清单、升级步骤 |
| `mcp-server/pyproject.toml` | 新建 | T1.1 | P-07：锁定依赖；AgentCore CLI 打 CodeZip 时只读 `[project].dependencies` |
| `mcp-server/src/config/loader.py` | 修改 1 行 | T1.2 | P-02：`ClusterConfig.fe_http_port` |
| `mcp-server/src/store/store.py`、`bootstrap.py` | 修改 | T1.3 | P-03：进程级服务凭证兜底 |
| `mcp-server/src/server.py` | 修改 6 处 | T1.4 | P-04：`create_server(service_credentials=, workspace_dir=)` |
| `mcp-server/src/tools/profile.py` | 新建 | T1.5 | P-05：`list_recent_queries`、`get_query_profile`、`summarize_profile`、`register_profile_tools` |
| `mcp-server/config/mcp-server.toml` | 新建 | T1.6 | P-06：运行参数（超时、连接池、行数上限）|
| `mcp-server/src/agentcore_ext/{__init__,settings}.py` | 新建 | T1.6 | P-01：env / Secrets Manager → `Settings` |
| `mcp-server/src/agentcore_ext/app.py` | 新建（T1.6）→ 完整版（T1.7）| T1.6、T1.7 | P-01：`build_server`；T1.7 加 `/ping`、`configure_logging`、`main` |
| `mcp-server/mcp_server.py` | 新建 | T1.7 | P-01：AgentCore 入口 |
| `mcp-server/test/test_agentcore_*.py` | 新建 | T1.2–T1.7 | P-08：config 4 / store_creds 9 / service_mode 10 / profile 29 / settings 13 / tools 6 / app 6 = 77 个测试 |
| `scripts/mcp_smoke.py` | 修改 | T1.8 | 新增 `flow` 子命令（profile 流程 + 错误情况）|

常用测试命令（T1.1 之后都可用）：

```bash
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3   # upstream 离线测试
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py'               # 本项目新增的测试
```

---

### Task T1.1：vendoring upstream + pyproject（P-07）+ 基线测试

**Files:**
- Create：`mcp-server/` 下的 upstream 文件（`git archive`）、`mcp-server/UPSTREAM.md`、`mcp-server/pyproject.toml`
- Modify：`tasks.md`、`progress.md`

**Interfaces:**
- Produces：`mcp-server/src`（upstream 包根，测试里用 `sys.path.insert(0, <mcp-server>/src)` 导入 `server`、`store.store`、`config.loader`、`core.*`）；`.venv` 里装好全部锁定依赖；后续任务的「upstream 原始版本」= 本任务的 commit（`git diff <本任务 commit> -- mcp-server/src` 就是全部补丁）

- [ ] **Step 1：确认前置条件**

```bash
git status --short | head -5          # 期望：无输出（工作区干净）
ls .venv/bin/python || uv venv .venv --python 3.12   # .venv 由 T0.1 创建；P1 先于 T0.1 执行时在这里建
.venv/bin/python --version            # 期望：Python 3.12.x
test ! -e mcp-server && echo "mcp-server/ not present yet"
```

- [ ] **Step 2：vendoring**

```bash
rm -rf /tmp/velodb-vendor
git clone --quiet https://github.com/velodb/velodb-mcp-server.git /tmp/velodb-vendor
git -C /tmp/velodb-vendor describe --tags f235832      # 期望：velodb-mcp-server-0.3.0
mkdir -p mcp-server
git -C /tmp/velodb-vendor archive f235832 src test LICENSE.txt NOTICE mcp-server.toml requirements.txt | tar -x -C mcp-server/
find mcp-server -type f | wc -l                        # 期望：594
ls mcp-server mcp-server/src
```
期望：`mcp-server` 下有 `LICENSE.txt NOTICE mcp-server.toml requirements.txt src test`；`src` 下有 `auth config core main.py metricflow server.py skills store tools`。

- [ ] **Step 3：写 `mcp-server/UPSTREAM.md`**

```markdown
# Upstream

- Repository: https://github.com/velodb/velodb-mcp-server
- Commit: `f235832da69f30194574defa370fa793aa14a340` (tag `velodb-mcp-server-0.3.0`, 2026-08-31; its pyproject still says 0.2.6)
- Vendored with `git archive f235832 src test LICENSE.txt NOTICE mcp-server.toml requirements.txt`,
  committed unmodified first. Each patch below is a separate commit on top.
- License: Apache License 2.0 (`LICENSE.txt`, `NOTICE`).

## AgentCore patches (specs/doris-mcp-quick/design.md §5.2)

| # | Files | Change |
|---|---|---|
| P-01 | `mcp_server.py`, `src/agentcore_ext/` (new) | AgentCore entrypoint: settings from env / Secrets Manager, `build_server`, `GET /ping`, stderr logging, `main` |
| P-02 | `src/config/loader.py` | `ClusterConfig.fe_http_port` |
| P-03 | `src/store/store.py`, `src/store/bootstrap.py` | process-wide service credentials as a fallback for the store layer |
| P-04 | `src/server.py` | `create_server(service_credentials=, workspace_dir=)`: no MCP auth, one service-account pool |
| P-05 | `src/tools/profile.py` (new) | `list_recent_queries`, `get_query_profile` |
| P-06 | `config/mcp-server.toml` (new) | runtime limits (50 s SQL timeout, pool 5, 2000 rows) |
| P-07 | `pyproject.toml` (new) | dependencies pinned to upstream `uv.lock` + boto3, for AgentCore CodeZip |
| P-08 | `test/test_agentcore_*.py` (new) | tests for P-01..P-06 |

Only P-02, P-03 and P-04 touch upstream files; without service credentials they behave exactly like upstream.

## Upgrading upstream

1. `git archive <new-commit> src test LICENSE.txt NOTICE mcp-server.toml requirements.txt` into a scratch dir and diff it against the vendored commit.
2. Replace the vendored files, then re-apply P-02/P-03/P-04 (`git log --oneline -- mcp-server/src` lists their commits).
3. Update the pins in `pyproject.toml` from the new `uv.lock`, then run the upstream offline suite and `test_agentcore_*.py`.
```

- [ ] **Step 4：写 `mcp-server/pyproject.toml`（P-07）**

```toml
[project]
name = "doris-mcp-agentcore"
version = "0.1.0"
description = "velodb-mcp-server @f235832 + AgentCore patches (see UPSTREAM.md)"
requires-python = ">=3.12"
# Pinned to upstream uv.lock @f235832 (+ mcp/starlette from the same lock, + boto3).
# The AgentCore CLI installs these with: uv pip install -r pyproject.toml --target <staging>
#   --python-version 3.12 --python-platform aarch64-manylinux* --only-binary :all:
dependencies = [
    "aiomysql==0.3.2",
    "authlib==1.7.2",
    "boto3==1.43.103",
    "cryptography==49.0.0",
    "fastmcp==3.4.4",
    "httpx==0.28.1",
    "importlib_metadata==9.0.0",
    "jinja2==3.1.6",
    "jsonschema==4.26.0",
    "mcp==1.28.1",
    "more-itertools==11.1.0",
    "pydantic==2.13.4",
    "pyjwt==2.13.0",
    "pymysql==1.2.0",
    "python-dateutil==2.9.0.post0",
    "python-dotenv==1.2.2",
    "python-multipart==0.0.32",
    "pyyaml==6.0.3",
    "rapidfuzz==3.14.5",
    "sqlglot==30.13.0",
    "starlette==1.3.1",
    "tabulate==0.10.0",
    "tomli==2.4.1",
    "typer==0.27.0",
    "typing_extensions==4.16.0",
    "uvicorn==0.51.0",
]
```

- [ ] **Step 5：安装依赖到 `.venv`**

```bash
uv pip install --python .venv/bin/python -r mcp-server/pyproject.toml
.venv/bin/python -c "import fastmcp, mcp, starlette, boto3, httpx; print(fastmcp.__version__, starlette.__version__, httpx.__version__)"
```
期望：`3.4.4 1.3.1 0.28.1`。

- [ ] **Step 6：upstream 基线离线测试**

```bash
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3
```
期望：最后是 `🎉 All tests passed!`。如果 `test_deps.py` 报找不到 `requirements.txt`，说明 Step 2 漏了这个文件（`test_deps.py` 从 `mcp-server/requirements.txt` 读依赖清单）。

- [ ] **Step 7：aarch64 wheel 检查（模拟 AgentCore CLI 打包）**

```bash
rm -rf /tmp/cz-check
uv pip install -q -r mcp-server/pyproject.toml --target /tmp/cz-check \
  --python-version 3.12 --python-platform aarch64-manylinux_2_28 --only-binary :all:
du -sh /tmp/cz-check; rm -rf /tmp/cz-check
```
期望：安装成功，约 107 MB（CodeZip 上限 250 MB）。说明：AgentCore CLI 0.30.0 先试 `aarch64-manylinux2014`，`rapidfuzz==3.14.5` 没有这个平台的 wheel，CLI 会自动回退到 `manylinux_2_28`，这是预期行为，不需要处理。

- [ ] **Step 8：确认 git 只会收录源码**

```bash
.venv/bin/python -c "import sys; sys.path.insert(0, 'mcp-server/src'); import server"   # 产生 __pycache__
git status --short --untracked-files=all mcp-server | grep -c . # 期望：596（594 个 upstream 文件 + UPSTREAM.md + pyproject.toml）
git status --short --untracked-files=all mcp-server | grep -E "__pycache__|workspace/|agentcore/" || echo "clean"
```
期望：`clean`（`.gitignore` 已忽略 `__pycache__/`、`mcp-server/workspace/`、`mcp-server/agentcore/`）。

- [ ] **Step 9：收尾**

勾选 T1.1；progress 记录：安装的 fastmcp/starlette 版本、离线测试通过、aarch64 wheel 体积。

```bash
bash scripts/check-secrets.sh          # 期望：check-secrets: OK
git add mcp-server specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "vendor: velodb-mcp-server @f235832 (unmodified) + pyproject pins (P-07)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git log -1 --format=%h                 # 记进 progress：这是「upstream 原始版本」的 commit
```

---

### Task T1.2：P-02 `ClusterConfig.fe_http_port`

**Files:**
- Modify：`mcp-server/src/config/loader.py:60`（`fe_mysql_port` 下一行）
- Test：`mcp-server/test/test_agentcore_config.py`

**Interfaces:**
- Produces：`AppConfig(config_dir).cluster.fe_http_port: int`（默认 8030，读取 `[server].fe_http_port`，字符串会转成 int）；T1.6 的 `build_server` 用 settings 覆盖它

- [ ] **Step 1：写失败的测试 `mcp-server/test/test_agentcore_config.py`**

```python
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
```

- [ ] **Step 2：运行，确认失败**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_config.py`
期望：4 个 ERROR，`AttributeError: 'ClusterConfig' object has no attribute 'fe_http_port'`。

- [ ] **Step 3：实现**

`mcp-server/src/config/loader.py`，找到：
```python
        self.fe_mysql_port: int = server.get("fe_port", 9030)
```
在它下面加一行，变成：
```python
        self.fe_mysql_port: int = server.get("fe_port", 9030)
        self.fe_http_port: int = int(server.get("fe_http_port", 8030))
```

- [ ] **Step 4：运行，确认通过**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_config.py`
期望：`Ran 4 tests` / `OK`。再跑 upstream 离线测试，期望仍是 `🎉 All tests passed!`。

- [ ] **Step 5：收尾**

```bash
git diff --stat                        # 期望：只有 loader.py 1 行
bash scripts/check-secrets.sh
git add mcp-server/src/config/loader.py mcp-server/test/test_agentcore_config.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "patch(P-02): ClusterConfig.fe_http_port

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T1.3：P-03 store / bootstrap 服务账号兜底

**Files:**
- Modify：`mcp-server/src/store/store.py`（`set_request_credentials` 之后插入一段；`_get_conn` 改 1 行）
- Modify：`mcp-server/src/store/bootstrap.py`（`pre_validate_physical` 里 import 1 行、取凭证 1 行）
- Test：`mcp-server/test/test_agentcore_store_creds.py`

**Interfaces:**
- Produces（`store.store`）：
  - `set_service_credentials(user: str, password: str) -> None`
  - `clear_service_credentials() -> None`
  - `get_effective_credentials() -> tuple[str, str] | None`：请求凭证（contextvar `_request_creds`）优先，其次服务凭证，都没有返回 `None`
- 行为：没设服务凭证时，`_get_conn()` 仍抛 `RuntimeError`，`pre_validate_physical` 仍返回 `(False, "No Doris credentials available …")`（upstream 的 `test_credential_pass.py` 锁定了这一行为）
- 已知不改：store.py 第 238/289/567 行记录 `updated_by` 时仍只读请求凭证（service 模式下记为 `system`）；这些是语义模型发布路径，Runtime 上不会走到

- [ ] **Step 1：写失败的测试 `mcp-server/test/test_agentcore_store_creds.py`**

```python
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
```

- [ ] **Step 2：运行，确认失败**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_store_creds.py`
期望：`Ran 9 tests`，`FAILED (errors=16)`（每个测试的 `tearDown` 也会报错，所以错误数多于测试数），全部是 `AttributeError: module 'store.store' has no attribute 'clear_service_credentials'`（或 `set_service_credentials` / `get_effective_credentials`）。

- [ ] **Step 3：实现 `store.py`**

`mcp-server/src/store/store.py`，找到：
```python
    _request_creds.set((user, password))


def set_doris_endpoint(host: str, port: int) -> None:
```
替换为：
```python
    _request_creds.set((user, password))


# Process-wide fallback credentials (AgentCore service mode). Request
# credentials, when present, always win; with neither set, _get_conn() keeps
# raising RuntimeError exactly as upstream does.
_service_creds: tuple[str, str] | None = None


def set_service_credentials(user: str, password: str) -> None:
    """Install the service-account credentials used when a request carries none."""
    global _service_creds
    _service_creds = (user, password)


def clear_service_credentials() -> None:
    global _service_creds
    _service_creds = None


def get_effective_credentials() -> tuple[str, str] | None:
    """Request credentials first, then service credentials, else None."""
    return _request_creds.get() or _service_creds


def set_doris_endpoint(host: str, port: int) -> None:
```

同一文件，找到 `_get_conn` 里的（整个文件唯一一处以 4 个空格缩进的 `creds = _request_creds.get()`）：
```python
def _get_conn() -> pymysql.Connection:
    creds = _request_creds.get()
```
替换为：
```python
def _get_conn() -> pymysql.Connection:
    creds = get_effective_credentials()
```

- [ ] **Step 4：实现 `bootstrap.py`**

`mcp-server/src/store/bootstrap.py`（`pre_validate_physical` 内），找到：
```python
    from store.store import _DORIS_HOST, _DORIS_PORT, _request_creds
```
替换为：
```python
    from store.store import _DORIS_HOST, _DORIS_PORT, get_effective_credentials
```
同一函数，找到：
```python
        creds = _request_creds.get()
```
替换为：
```python
        creds = get_effective_credentials()
```

- [ ] **Step 5：运行，确认通过**

```bash
.venv/bin/python -m unittest mcp-server/test/test_agentcore_store_creds.py mcp-server/test/test_agentcore_config.py
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3
grep -n "_request_creds" mcp-server/src/store/bootstrap.py || echo "bootstrap no longer reads _request_creds directly"
```
期望：`Ran 13 tests` / `OK`；`🎉 All tests passed!`（其中 upstream `test_credential_pass.py` 不变且通过）；最后一行打印 `bootstrap no longer reads _request_creds directly`。

- [ ] **Step 6：收尾**

```bash
git diff --stat                        # 期望：store.py、bootstrap.py
bash scripts/check-secrets.sh
git add mcp-server/src/store/store.py mcp-server/src/store/bootstrap.py mcp-server/test/test_agentcore_store_creds.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "patch(P-03): store/bootstrap fall back to process-wide service credentials

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T1.4：P-04 `create_server(service_credentials=, workspace_dir=)`

**Files:**
- Modify：`mcp-server/src/server.py`（6 处，都在 `create_server` 内）
- Test：`mcp-server/test/test_agentcore_service_mode.py`

**Interfaces:**
- Consumes：T1.3 的 `set_service_credentials` / `clear_service_credentials`
- Produces：`create_server(config_dir=None, env_file=None, machine_ip=None, config=None, service_credentials: tuple[str, str] | None = None, workspace_dir: str | None = None) -> FastMCP`
  - `service_credentials` 非空：`mcp.auth is None`；`_get_per_user_pool()` 直接返回 `pool_manager.get_or_create_local_pool(user, password)`；store 层兜底凭证 = 该账号
  - `service_credentials` 为空：与 upstream 完全一致（`CredentialVerifier`），并清掉进程里残留的服务凭证
  - workspace 目录：参数 → `$DORIS_MCP_WORKSPACE_DIR` → upstream 默认 `<config_dir 的上级>/workspace`，并 `abspath`；目录下会创建 `workspaces/` 和 `logs/`

- [ ] **Step 1：写失败的测试 `mcp-server/test/test_agentcore_service_mode.py`**

```python
"""P-04: create_server(service_credentials=, workspace_dir=) for AgentCore.

Service mode: no MCP-level auth (Runtime IAM / Gateway JWT guard the edge),
every tool uses one service-account pool, and the store layer falls back to
the same credentials. Without service credentials upstream behavior is kept.
"""

import contextvars
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client  # noqa: E402

import store.store as st  # noqa: E402
from config.loader import AppConfig  # noqa: E402
from server import create_server  # noqa: E402

SVC = ("mcp_svc", "svc-pw")


class _ServerCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config_dir = self.root / "config"
        self.config_dir.mkdir()
        self.addCleanup(st.clear_service_credentials)

    def build(self, **kwargs):
        return create_server(config_dir=str(self.config_dir), config=AppConfig(self.config_dir), **kwargs)

    async def call_list_databases(self, server):
        async with Client(server) as client:
            result = await client.call_tool("list_databases", {}, raise_on_error=False)
        return json.loads(result.content[0].text)


class TestServiceMode(_ServerCase):
    async def test_service_mode_disables_mcp_auth(self):
        server = self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        self.assertIsNone(server.auth)

    async def test_service_mode_installs_store_fallback(self):
        self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        self.assertEqual(contextvars.Context().run(st.get_effective_credentials), SVC)

    async def test_tools_use_the_service_account_pool(self):
        server = self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        acquire = AsyncMock(side_effect=RuntimeError("doris unreachable"))
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", acquire):
            body = await self.call_list_databases(server)
        acquire.assert_awaited_once()
        self.assertEqual(acquire.await_args.args[:2], SVC)
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "CONNECTION_ERROR")

    async def test_service_password_not_in_error_payload(self):
        server = self.build(service_credentials=SVC, workspace_dir=str(self.root / "ws"))
        acquire = AsyncMock(side_effect=RuntimeError("doris unreachable"))
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", acquire):
            body = await self.call_list_databases(server)
        self.assertNotIn(SVC[1], json.dumps(body))


class TestUpstreamModeUnchanged(_ServerCase):
    async def test_default_mode_keeps_credential_verifier(self):
        server = self.build(workspace_dir=str(self.root / "ws"))
        self.assertIsNotNone(server.auth)

    async def test_default_mode_clears_stale_service_credentials(self):
        st.set_service_credentials(*SVC)
        self.build(workspace_dir=str(self.root / "ws"))
        self.assertIsNone(contextvars.Context().run(st.get_effective_credentials))

    async def test_default_mode_without_token_never_opens_a_pool(self):
        server = self.build(workspace_dir=str(self.root / "ws"))
        acquire = AsyncMock()
        with patch("core.pool_manager.PoolManager.get_or_create_local_pool", acquire):
            body = await self.call_list_databases(server)
        acquire.assert_not_awaited()
        self.assertFalse(body["success"])


class TestWorkspaceDir(_ServerCase):
    async def test_parameter_wins(self):
        self.build(workspace_dir=str(self.root / "ws"))
        self.assertTrue((self.root / "ws" / "workspaces").is_dir())
        self.assertTrue((self.root / "ws" / "logs").is_dir())
        self.assertFalse((self.root / "workspace").exists())

    async def test_env_var_used_when_no_parameter(self):
        with patch.dict(os.environ, {"DORIS_MCP_WORKSPACE_DIR": str(self.root / "env-ws")}):
            self.build()
        self.assertTrue((self.root / "env-ws" / "workspaces").is_dir())
        self.assertFalse((self.root / "workspace").exists())

    async def test_upstream_default_next_to_config_dir(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DORIS_MCP_WORKSPACE_DIR", None)
            self.build()
        self.assertTrue((self.root / "workspace" / "workspaces").is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2：运行，确认失败**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_service_mode.py`
期望：`Ran 10 tests`，`FAILED (failures=1, errors=8)`：8 个 `TypeError: create_server() got an unexpected keyword argument 'workspace_dir'`（或 `'service_credentials'`）；`test_env_var_used_when_no_parameter` 是 failure（upstream 不读这个环境变量）；`test_upstream_default_next_to_config_dir` 在 upstream 上本来就通过。

- [ ] **Step 3：实现（`mcp-server/src/server.py` 的 6 处修改）**

**3a 签名与 docstring**，找到：
```python
    config: "AppConfig | None" = None,
) -> FastMCP:
    """Create and configure the MCP server."""
```
替换为：
```python
    config: "AppConfig | None" = None,
    service_credentials: tuple[str, str] | None = None,
    workspace_dir: str | None = None,
) -> FastMCP:
    """Create and configure the MCP server.

    service_credentials: (user, password) of one Doris service account. When
    set, MCP-level auth is disabled (the AgentCore Runtime / Gateway guard the
    edge) and every tool and store operation uses that account.
    workspace_dir: writable directory for workspaces and logs; defaults to
    $DORIS_MCP_WORKSPACE_DIR, then <config_dir>/../workspace.
    """
```

**3b workspace 目录**，找到：
```python
    workspace_dir = os.path.join(os.path.dirname(config_path), "workspace")
```
替换为：
```python
    workspace_dir = os.path.abspath(
        workspace_dir
        or os.environ.get("DORIS_MCP_WORKSPACE_DIR")
        or os.path.join(os.path.dirname(config_path), "workspace")
    )
```

**3c 设置 / 清除服务凭证**，找到：
```python
    from store.store import set_doris_endpoint
    set_doris_endpoint(cc.fe_host, cc.fe_mysql_port)
```
替换为：
```python
    from store.store import clear_service_credentials, set_doris_endpoint, set_service_credentials
    set_doris_endpoint(cc.fe_host, cc.fe_mysql_port)
    if service_credentials is not None:
        set_service_credentials(*service_credentials)
    else:
        clear_service_credentials()
```

**3d 服务模式日志**，找到：
```python
    logger.info("Auth: CredentialVerifier registered (username:password, 10-min cache)")
```
替换为：
```python
    logger.info("Auth: CredentialVerifier registered (username:password, 10-min cache)")
    if service_credentials is not None:
        logger.info("Auth: service mode, MCP auth delegated to the edge; Doris user %s", service_credentials[0])
```
（`CredentialVerifier registered` 这一行在服务模式下也会打印，但 verifier 不会被挂到 FastMCP 上，见 3f。）

**3e 连接池走服务账号**（`_get_per_user_pool` 内），找到：
```python
            raise RuntimeError("PoolManager not initialized")
        from mcp.server.auth.middleware.auth_context import get_access_token
```
替换为：
```python
            raise RuntimeError("PoolManager not initialized")
        if service_credentials is not None:
            svc_user, svc_password = service_credentials
            return await pool_manager.get_or_create_local_pool(svc_user, svc_password)
        from mcp.server.auth.middleware.auth_context import get_access_token
```

**3f 服务模式下不挂 MCP 鉴权**，找到：
```python
        auth=auth_provider,
```
替换为：
```python
        auth=None if service_credentials is not None else auth_provider,
```

- [ ] **Step 4：运行，确认通过**

```bash
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py'
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3
git diff --stat                        # 期望：只有 server.py，约 +25/-3
```
期望：`Ran 23 tests` / `OK`；`🎉 All tests passed!`。

- [ ] **Step 5：收尾**

```bash
bash scripts/check-secrets.sh
git add mcp-server/src/server.py mcp-server/test/test_agentcore_service_mode.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "patch(P-04): create_server service mode (service_credentials, workspace_dir)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T1.5：P-05 profile 工具 `src/tools/profile.py`

**Files:**
- Create：`mcp-server/src/tools/profile.py`
- Test：`mcp-server/test/test_agentcore_profile.py`

**Interfaces:**
- Consumes：upstream `core.audit.log_tool_call`、`core.response.{ErrorCode, error_response, success_response}`、`core.sensitive_mask.mask_sensitive`
- Produces（T1.6 的 `build_server` 使用）：
  - `FeHttpTarget(base_url: str, user: str, password: str, timeout: float = 15.0)`（frozen dataclass，`password` 不进 `repr`）
  - `async list_recent_queries(target, limit=20, user="", sql_contains="", *, scope="all", transport=None) -> str`
  - `async get_query_profile(target, query_id, mode="summary", max_chars=20000, *, scope="all", transport=None) -> str`
  - `summarize_profile(text: str) -> str`
  - `register_profile_tools(mcp, target, scope="all", transport=None) -> None`：注册 `list_recent_queries`、`get_query_profile`（`readOnlyHint=True`），每次调用写审计日志
  - 返回值都是 upstream 格式的 JSON 字符串：`{"success": true, "data": …, "meta": …}` 或 `{"success": false, "error": {"code", "message"}}`
- Doris 4.1.4 行为（design §4.1，✅ 实测）：错误是 HTTP 200 + JSON `code`；v2 profile/text 只给自己的 profile（别人的是 `data:{}`）；`/api/profile/text` 返回任何用户的纯文本 profile，找不到时返回纯文本 `query id <id> not found`，id 格式不对返回 JSON `code:500 "Invalid profile id"`；真实 profile 里 `PhysicalPlan:` 在第 0 列，其下每个扫描表的每一列都有一行 `<col>#<id> -> ndv=…` 统计

- [ ] **Step 1：写失败的测试 `mcp-server/test/test_agentcore_profile.py`**

```python
"""P-05: Doris query-profile tools (src/tools/profile.py) against a mocked FE HTTP API.

The mock reproduces Doris 4.1.4 behavior measured in design §4.1: errors are
HTTP 200 + JSON {"code": ...}; v2 profile/text only serves the caller's own
profiles (others -> data: {}); /api/profile/text returns plain text, including
"query id <id> not found" for unknown ids (seen on the demo cluster in T1.8 drafting).
"""

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client, FastMCP  # noqa: E402

from tools.profile import (  # noqa: E402
    FeHttpTarget,
    get_query_profile,
    list_recent_queries,
    register_profile_tools,
    summarize_profile,
)

QID = "0123456789abcdef-fedcba9876543210"
OTHER_QID = "aaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb"
TARGET = FeHttpTarget("http://fe.test:8030", "mcp_svc", "s3cret-pw")

PROFILE = "\n".join([
    "Summary:",
    f"  - Profile ID: {QID}",
    "  - Task Type: QUERY",
    "  - Workload Group: N/A",
    "Execution Summary:",
    "  - Parse SQL Time: 1ms",
    "  - Plan Time: N/A",
    "ChangedSessionVariables:",
    "MergedProfile:",
    "  Fragments:",
    "    Fragment 0:",
    "      RESULT_SINK_OPERATOR(id=0):",
    "        - ExecTime: 1.2ms",
    "        - MemoryUsage: sum 0.00 , avg 0.00 , max 0.00 , min 0.00 ",
    "        - WaitForDependencyTime: avg 0ns, max 0ns, min 0ns",
    "        - InputRows: sum 0, avg 0, max 7, min 0",
    "        - group by: ",
    f"DetailProfile({QID}):",
    "  Fragments:",
    "    Fragment 0:",
    "      - InstanceId: 1",
    "      - InstanceId: 2",
    "Appendix:",
    "PhysicalPlan:",
    "PhysicalResultSink[182] ( outputExprs=[n#31] )",
    "     PhysicalOlapScan[158]@0 ( table=fact_order, stats=100,240 )",
    "       order_id#0 -> ndv=100201.0000, min=1.000000(1), max=9.000000(9), count=100240.0000",
    "       order_date#1 -> ndv=630.0000, min=20250101000000.000000(2025-01-01)",
    "       __DORIS_DELETE_SIGN__#27 -> unknown(1.0)",
    "     PhysicalFilter[162]@1 ( predicates=(__DORIS_DELETE_SIGN__#27 = 0) )",
])


def _row(qid, user, start, sql, db="ecom"):
    return {
        "Profile ID": qid, "Task Type": "QUERY", "Start Time": start, "End Time": start,
        "Total": "12ms", "Task State": "OK", "User": user, "Default Catalog": "internal",
        "Default Db": db, "Sql Statement": sql, "__hrefPaths": [],
    }


ROWS = [
    _row(OTHER_QID, "root", "2026-09-26 10:00:00", "SELECT 1"),
    _row(QID, "mcp_svc", "2026-09-26 11:00:00", "SELECT /*+SET_VAR(enable_profile=true)*/ 2 /* trace:AbC123 */"),
    _row("cccccccccccccccc-dddddddddddddddd", "mcp_svc", "2026-09-26 09:00:00", "SELECT " + "x, " * 200 + "1"),
]


def _ok(data):
    return httpx.Response(200, json={"msg": "success", "code": 0, "data": data, "count": 0})


class FakeFe:
    """Programmable FE HTTP API; records every request."""

    def __init__(self, v2=None, api_text=None, listing=None):
        self.requests: list[httpx.Request] = []
        self.v2 = v2 or (lambda qid: _ok({}))
        self.api_text = api_text or (lambda qid: httpx.Response(200, text=f"query id {qid} not found"))
        self.listing = listing or (lambda: _ok({"column_names": [], "rows": ROWS}))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/rest/v1/query_profile":
            return self.listing()
        if path.startswith("/rest/v2/manager/query/profile/text/"):
            return self.v2(path.rsplit("/", 1)[1])
        if path == "/api/profile/text":
            return self.api_text(request.url.params.get("query_id"))
        return httpx.Response(404, text="no route")

    def paths(self):
        return [r.url.path for r in self.requests]


def _body(result: str) -> dict:
    return json.loads(result)


class TestListRecentQueries(unittest.IsolatedAsyncioTestCase):
    async def test_newest_first_with_meta(self):
        fe = FakeFe()
        body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
        self.assertTrue(body["success"])
        ids = [q["query_id"] for q in body["data"]["queries"]]
        self.assertEqual(ids, [QID, OTHER_QID, "cccccccccccccccc-dddddddddddddddd"])
        self.assertEqual(body["meta"], {"returned": 3, "matched": 3, "source": "/rest/v1/query_profile"})
        first = body["data"]["queries"][0]
        self.assertEqual(
            set(first),
            {"query_id", "user", "default_db", "task_type", "state", "start_time", "end_time", "total", "sql"},
        )
        self.assertEqual(body["data"]["scope"], "all")

    async def test_sql_preview_is_capped_at_200_chars(self):
        body = _body(await list_recent_queries(TARGET, transport=FakeFe().transport()))
        self.assertTrue(all(len(q["sql"]) <= 200 for q in body["data"]["queries"]))

    async def test_filters_and_limit(self):
        fe = FakeFe()
        body = _body(await list_recent_queries(TARGET, limit=1, user="mcp_svc", transport=fe.transport()))
        self.assertEqual([q["query_id"] for q in body["data"]["queries"]], [QID])
        self.assertEqual(body["meta"]["matched"], 2)
        body = _body(await list_recent_queries(TARGET, sql_contains="abc123", transport=fe.transport()))
        self.assertEqual([q["query_id"] for q in body["data"]["queries"]], [QID])

    async def test_scope_self_forces_own_user(self):
        body = _body(await list_recent_queries(TARGET, user="root", scope="self", transport=FakeFe().transport()))
        self.assertEqual({q["user"] for q in body["data"]["queries"]}, {"mcp_svc"})
        self.assertEqual(body["data"]["scope"], "self")

    async def test_limit_out_of_range_makes_no_request(self):
        for limit in (0, 101):
            fe = FakeFe()
            body = _body(await list_recent_queries(TARGET, limit=limit, transport=fe.transport()))
            self.assertEqual(body["error"]["code"], "INVALID_PARAMS")
            self.assertEqual(fe.requests, [])

    async def test_sends_basic_auth(self):
        fe = FakeFe()
        await list_recent_queries(TARGET, transport=fe.transport())
        expected = "Basic " + base64.b64encode(b"mcp_svc:s3cret-pw").decode()
        self.assertEqual(fe.requests[0].headers["authorization"], expected)

    async def test_body_code_401_is_unauthenticated(self):
        fe = FakeFe(listing=lambda: httpx.Response(
            200, json={"msg": "Unauthorized", "code": 401, "data": "Access denied for mcp_svc"}))
        body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
        self.assertEqual(body["error"]["code"], "UNAUTHENTICATED")
        self.assertNotIn("s3cret-pw", json.dumps(body))

    async def test_http_401_is_unauthenticated(self):
        fe = FakeFe(listing=lambda: httpx.Response(401, text="denied"))
        body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
        self.assertEqual(body["error"]["code"], "UNAUTHENTICATED")

    async def test_http_500_and_non_json_are_connection_errors(self):
        for resp in (httpx.Response(500, text="boom"), httpx.Response(200, text="<html>")):
            fe = FakeFe(listing=lambda resp=resp: resp)
            body = _body(await list_recent_queries(TARGET, transport=fe.transport()))
            self.assertEqual(body["error"]["code"], "CONNECTION_ERROR")

    async def test_timeout_and_connect_errors(self):
        def raise_timeout(request):
            raise httpx.ReadTimeout("slow", request=request)

        def raise_connect(request):
            raise httpx.ConnectError("refused", request=request)

        for handler, code in ((raise_timeout, "QUERY_TIMEOUT"), (raise_connect, "CONNECTION_ERROR")):
            body = _body(await list_recent_queries(TARGET, transport=httpx.MockTransport(handler)))
            self.assertEqual(body["error"]["code"], code)
            self.assertNotIn("s3cret-pw", json.dumps(body))


class TestGetQueryProfile(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_query_ids_make_no_request(self):
        for qid in ("", "abc", "../../api/x", QID + "/../x", "0123456789abcdeg-fedcba9876543210"):
            fe = FakeFe()
            body = _body(await get_query_profile(TARGET, qid, transport=fe.transport()))
            self.assertEqual(body["error"]["code"], "INVALID_PARAMS", qid)
            self.assertEqual(fe.requests, [])

    async def test_invalid_mode_and_max_chars(self):
        fe = FakeFe()
        for kwargs in ({"mode": "brief"}, {"max_chars": 999}, {"max_chars": 200001}):
            body = _body(await get_query_profile(TARGET, QID, transport=fe.transport(), **kwargs))
            self.assertEqual(body["error"]["code"], "INVALID_PARAMS", kwargs)
        self.assertEqual(fe.requests, [])

    async def test_v2_hit_returns_summary(self):
        fe = FakeFe(v2=lambda qid: _ok({"profile": PROFILE}))
        body = _body(await get_query_profile(TARGET, f"  {QID.upper()} ", transport=fe.transport()))
        data = body["data"]
        self.assertTrue(data["profile_found"])
        self.assertEqual((data["query_id"], data["source"], data["mode"]), (QID, "v2", "summary"))
        self.assertEqual(data["total_chars"], len(PROFILE))
        self.assertFalse(data["truncated"])
        self.assertEqual(data["returned_chars"], len(data["profile_text"]))
        self.assertNotIn("InstanceId", data["profile_text"])
        self.assertIn("ExecTime", data["profile_text"])
        self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{QID}"])

    async def test_full_mode_returns_everything(self):
        fe = FakeFe(v2=lambda qid: _ok({"profile": PROFILE}))
        data = _body(await get_query_profile(TARGET, QID, mode="full", transport=fe.transport()))["data"]
        self.assertEqual(data["profile_text"], PROFILE)

    async def test_falls_back_to_api_text_for_other_users_profiles(self):
        fe = FakeFe(api_text=lambda qid: httpx.Response(200, text=PROFILE, headers={"content-type": "text/plain"}))
        data = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))["data"]
        self.assertTrue(data["profile_found"])
        self.assertEqual(data["source"], "api_text")
        self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{QID}", "/api/profile/text"])
        self.assertEqual(fe.requests[1].url.params["query_id"], QID)

    async def test_scope_self_never_uses_api_text(self):
        fe = FakeFe(api_text=lambda qid: httpx.Response(200, text=PROFILE))
        body = _body(await get_query_profile(TARGET, QID, scope="self", transport=fe.transport()))
        self.assertFalse(body["data"]["profile_found"])
        self.assertEqual(fe.paths(), [f"/rest/v2/manager/query/profile/text/{QID}"])

    async def test_not_found_is_evidence_not_error(self):
        fe = FakeFe()
        body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
        self.assertTrue(body["success"])
        self.assertEqual(body["data"], {"query_id": QID, "profile_found": False})
        self.assertIn("enable_profile", body["meta"]["hint"])
        self.assertEqual(body["meta"]["evidence"]["v2"]["code"], 0)
        self.assertEqual(body["meta"]["evidence"]["api_text"], {"code": None, "msg": f"query id {QID} not found"})

    async def test_api_text_json_error_is_not_found(self):
        fe = FakeFe(api_text=lambda qid: httpx.Response(200, json={"msg": "Invalid profile id", "code": 500}))
        body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
        self.assertFalse(body["data"]["profile_found"])
        self.assertEqual(body["meta"]["evidence"]["api_text"], {"code": 500, "msg": "Invalid profile id"})

    async def test_api_text_must_start_with_a_section_to_count_as_a_profile(self):
        for text in ("", "   ", "profile is not ready yet", "<html>error</html>"):
            fe = FakeFe(api_text=lambda qid, text=text: httpx.Response(200, text=text))
            body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
            self.assertFalse(body["data"]["profile_found"], repr(text))

    async def test_truncation(self):
        long_profile = "Summary:\n" + "\n".join(f"  - Counter{i}: {i}" for i in range(1, 501))
        fe = FakeFe(v2=lambda qid: _ok({"profile": long_profile}))
        data = _body(await get_query_profile(TARGET, QID, max_chars=1000, transport=fe.transport()))["data"]
        self.assertTrue(data["truncated"])
        self.assertEqual(data["returned_chars"], 1000)
        self.assertTrue(data["profile_text"].startswith(long_profile[:1000]))
        self.assertIn("truncated", data["profile_text"][1000:])

    async def test_v2_unauthorized(self):
        fe = FakeFe(v2=lambda qid: httpx.Response(200, json={"msg": "Unauthorized", "code": 401, "data": "x"}))
        body = _body(await get_query_profile(TARGET, QID, transport=fe.transport()))
        self.assertEqual(body["error"]["code"], "UNAUTHENTICATED")
        self.assertEqual(len(fe.requests), 1)


class TestSummarizeProfile(unittest.TestCase):
    def test_drops_detail_profile_and_na_lines(self):
        summary = summarize_profile(PROFILE)
        lines = summary.splitlines()
        self.assertIn(f"DetailProfile({QID}):", lines)
        self.assertIn("  [4 lines omitted; use mode='full' for per-instance detail]", lines)
        self.assertNotIn("InstanceId", summary)
        self.assertNotIn(": N/A", summary)
        for kept in ("Summary:", "Execution Summary:", "MergedProfile:", "Appendix:", "PhysicalPlan:"):
            self.assertIn(kept, lines)

    def test_drops_all_zero_counters_only(self):
        lines = summarize_profile(PROFILE).splitlines()
        self.assertNotIn("        - MemoryUsage: sum 0.00 , avg 0.00 , max 0.00 , min 0.00 ", lines)
        self.assertNotIn("        - WaitForDependencyTime: avg 0ns, max 0ns, min 0ns", lines)
        self.assertIn("        - InputRows: sum 0, avg 0, max 7, min 0", lines)
        self.assertIn("        - group by: ", lines)
        self.assertIn("        - ExecTime: 1.2ms", lines)

    def test_collapses_plan_column_statistics(self):
        lines = summarize_profile(PROFILE).splitlines()
        self.assertEqual(lines[-4:], [
            "PhysicalResultSink[182] ( outputExprs=[n#31] )",
            "     PhysicalOlapScan[158]@0 ( table=fact_order, stats=100,240 )",
            "       [3 column-statistics lines omitted; use mode='full' for column statistics]",
            "     PhysicalFilter[162]@1 ( predicates=(__DORIS_DELETE_SIGN__#27 = 0) )",
        ])

    def test_detail_profile_at_end(self):
        text = "Summary:\n  - A: 1\nDetailProfile(x):\n  - B: 2\n  - C: 3"
        self.assertEqual(
            summarize_profile(text),
            "Summary:\n  - A: 1\nDetailProfile(x):\n  [2 lines omitted; use mode='full' for per-instance detail]",
        )

    def test_text_without_sections_is_kept(self):
        self.assertEqual(summarize_profile("plain line\n  - X: 1"), "plain line\n  - X: 1")


class TestFeHttpTarget(unittest.TestCase):
    def test_repr_hides_password(self):
        self.assertNotIn("s3cret-pw", repr(TARGET))


class TestRegisterProfileTools(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_registered_read_only_and_audited(self):
        mcp = FastMCP("t")
        fe = FakeFe(v2=lambda qid: _ok({"profile": PROFILE}))
        register_profile_tools(mcp, TARGET, scope="all", transport=fe.transport())
        for name in ("list_recent_queries", "get_query_profile"):
            tool = await mcp.get_tool(name)
            self.assertTrue(tool.annotations.readOnlyHint, name)
            self.assertFalse(tool.annotations.destructiveHint, name)
        with patch("tools.profile.log_tool_call") as audit:
            async with Client(mcp) as client:
                result = await client.call_tool("get_query_profile", {"query_id": QID})
        self.assertTrue(json.loads(result.content[0].text)["data"]["profile_found"])
        audit.assert_called_once()
        self.assertEqual(audit.call_args.args[0], "get_query_profile")
        self.assertTrue(audit.call_args.kwargs["success"])

    async def test_mode_is_an_enum_in_the_schema(self):
        mcp = FastMCP("t")
        register_profile_tools(mcp, TARGET)
        tool = await mcp.get_tool("get_query_profile")
        self.assertEqual(sorted(tool.parameters["properties"]["mode"]["enum"]), ["full", "summary"])
        self.assertEqual(tool.parameters["required"], ["query_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2：运行，确认失败**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_profile.py`
期望：`ImportError`/`ModuleNotFoundError: No module named 'tools.profile'`。

- [ ] **Step 3：实现 `mcp-server/src/tools/profile.py`**

```python
"""Doris query-profile tools: list_recent_queries, get_query_profile.

Doris serves query profiles over the FE HTTP API, not over SQL. Behavior of
Doris 4.1.4 that this module relies on (measured, specs/doris-mcp-quick/design.md §4.1):

  * errors come back as HTTP 200 with a JSON body {"code": <non-zero>, "msg": ...};
  * GET /rest/v1/query_profile lists the collected profiles of all users, also
    for non-admin accounts;
  * GET /rest/v2/manager/query/profile/text/<query_id> serves only the caller's
    own profiles (anything else -> {"code": 0, "data": {}}), text in data.profile;
  * GET /api/profile/text?query_id=<query_id> returns any user's profile as plain
    text, and plain text "query id <query_id> not found" for unknown ids.

Every request is a read-only GET authenticated with HTTP Basic as the Doris
account the server runs as. Profiles are only collected for queries run with
profiling on, e.g. SELECT /*+SET_VAR(enable_profile=true)*/ ...
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from mcp.types import ToolAnnotations

from core.audit import log_tool_call
from core.response import ErrorCode, error_response, success_response
from core.sensitive_mask import mask_sensitive

_LIST_PATH = "/rest/v1/query_profile"
_V2_TEXT_PATH = "/rest/v2/manager/query/profile/text/{query_id}"
_API_TEXT_PATH = "/api/profile/text"

_QUERY_ID_RE = re.compile(r"^[0-9a-f]{16}-[0-9a-f]{16}$")
_SECTION_RE = re.compile(r"^([A-Za-z][A-Za-z ]*)(\([^)]*\))?:\s*$")
_COUNTER_RE = re.compile(r"^\s*- [^:]+: (.*)$")
_ZERO_VALUE_RE = re.compile(
    r"(?:(?:sum|avg|max|min)\s+)?0(?:\.0+)?\s*[A-Za-z]*\s*"
    r"(?:,\s*(?:sum|avg|max|min)\s+0(?:\.0+)?\s*[A-Za-z]*\s*)*"
)
_COLUMN_STATS_RE = re.compile(r"^(\s+)\S+#\d+ -> ")
_SQL_PREVIEW_CHARS = 200
_NOT_FOUND_HINT = (
    "No profile for this query_id. Profiles exist only for queries run with "
    "SELECT /*+SET_VAR(enable_profile=true)*/ ...; they can also be evicted. "
    "Use list_recent_queries to find valid query_ids."
)

Scope = Literal["all", "self"]


@dataclass(frozen=True)
class FeHttpTarget:
    """Doris FE HTTP endpoint plus the account used for Basic auth."""

    base_url: str
    user: str
    password: str = field(repr=False)
    timeout: float = 15.0


class _FeError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code


async def _fe_get(
    target: FeHttpTarget,
    path: str,
    params: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """GET path on the FE; transport/HTTP-level failures raise _FeError."""
    try:
        async with httpx.AsyncClient(
            base_url=target.base_url,
            auth=(target.user, target.password),
            timeout=target.timeout,
            transport=transport,
        ) as client:
            resp = await client.get(path, params=params)
    except httpx.TimeoutException as e:
        raise _FeError(ErrorCode.QUERY_TIMEOUT, f"Doris FE HTTP {path} timed out after {target.timeout:g}s") from e
    except httpx.HTTPError as e:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} unreachable: {type(e).__name__}") from e
    if resp.status_code in (401, 403):
        raise _FeError(ErrorCode.UNAUTHENTICATED, f"Doris FE HTTP rejected the credentials (HTTP {resp.status_code})")
    if resp.status_code != 200:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned HTTP {resp.status_code}")
    return resp


def _json_body(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        body = resp.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _raise_for_auth(body: dict[str, Any]) -> None:
    if body.get("code") == 401 or str(body.get("msg", "")).lower() == "unauthorized":
        raise _FeError(ErrorCode.UNAUTHENTICATED, "Doris FE HTTP rejected the credentials (code 401)")


def _checked_json(resp: httpx.Response, path: str) -> dict[str, Any]:
    """JSON body with code == 0, else _FeError."""
    body = _json_body(resp)
    if body is None:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned a non-JSON body")
    _raise_for_auth(body)
    if body.get("code") != 0:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned code={body.get('code')}: {body.get('msg')}")
    return body


def _query_row(row: dict[str, Any]) -> dict[str, Any]:
    sql = mask_sensitive(str(row.get("Sql Statement") or ""))
    if len(sql) > _SQL_PREVIEW_CHARS:
        sql = sql[: _SQL_PREVIEW_CHARS - 3] + "..."
    return {
        "query_id": row.get("Profile ID"),
        "user": row.get("User"),
        "default_db": row.get("Default Db"),
        "task_type": row.get("Task Type"),
        "state": row.get("Task State"),
        "start_time": row.get("Start Time"),
        "end_time": row.get("End Time"),
        "total": row.get("Total"),
        "sql": sql,
    }


async def list_recent_queries(
    target: FeHttpTarget,
    limit: int = 20,
    user: str = "",
    sql_contains: str = "",
    *,
    scope: Scope = "all",
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Newest-first list of queries that have a collected profile."""
    if not 1 <= limit <= 100:
        return error_response(ErrorCode.INVALID_PARAMS, "limit must be between 1 and 100")
    if scope == "self":
        user = target.user
    try:
        body = _checked_json(await _fe_get(target, _LIST_PATH, transport=transport), _LIST_PATH)
    except _FeError as e:
        return error_response(e.code, str(e))

    data = body.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    needle = sql_contains.lower()
    matched = [
        r for r in rows or []
        if isinstance(r, dict)
        and (not user or r.get("User") == user)
        and (not needle or needle in str(r.get("Sql Statement") or "").lower())
    ]
    matched.sort(key=lambda r: str(r.get("Start Time") or ""), reverse=True)
    queries = [_query_row(r) for r in matched[:limit]]
    return success_response(
        {"queries": queries, "scope": scope},
        {"returned": len(queries), "matched": len(matched), "source": _LIST_PATH},
    )


async def _profile_via_v2(
    target: FeHttpTarget, qid: str, transport: httpx.AsyncBaseTransport | None
) -> tuple[str | None, dict[str, Any]]:
    path = _V2_TEXT_PATH.format(query_id=qid)
    body = _json_body(await _fe_get(target, path, transport=transport))
    if body is None:
        raise _FeError(ErrorCode.CONNECTION_ERROR, f"Doris FE HTTP {path} returned a non-JSON body")
    _raise_for_auth(body)
    evidence = {"code": body.get("code"), "msg": body.get("msg")}
    data = body.get("data")
    profile = data.get("profile") if isinstance(data, dict) else None
    if body.get("code") == 0 and isinstance(profile, str) and profile.strip():
        return profile, evidence
    return None, evidence


async def _profile_via_api_text(
    target: FeHttpTarget, qid: str, transport: httpx.AsyncBaseTransport | None
) -> tuple[str | None, dict[str, Any]]:
    resp = await _fe_get(target, _API_TEXT_PATH, params={"query_id": qid}, transport=transport)
    body = _json_body(resp)
    if body is None:
        text = resp.text
        if _SECTION_RE.match(text.lstrip().split("\n", 1)[0]):
            return text, {"code": 0, "msg": "text"}
        # e.g. "query id <id> not found" for unknown or evicted ids
        return None, {"code": None, "msg": text.strip()[:200] or "empty body"}
    _raise_for_auth(body)
    data = body.get("data")
    if body.get("code") == 0 and isinstance(data, str) and data.strip():
        return data, {"code": 0, "msg": body.get("msg")}
    # e.g. {"code": 500, "msg": "Invalid profile id"} for malformed ids
    return None, {"code": body.get("code"), "msg": body.get("msg")}


def _is_empty_counter(line: str) -> bool:
    """A counter line whose value is N/A or zero in every aggregate."""
    if line.rstrip().endswith(": N/A"):
        return True
    counter = _COUNTER_RE.match(line)
    value = counter.group(1).strip() if counter else ""
    return bool(value) and _ZERO_VALUE_RE.fullmatch(value) is not None


def summarize_profile(text: str) -> str:
    """Shrink a profile to what is needed to find the slow operator.

    Top-level sections start in column 0 (Summary:, Execution Summary:,
    ChangedSessionVariables:, MergedProfile:, DetailProfile(<id>):, Appendix:,
    PhysicalPlan:); their contents are indented. Omitted:
      * the per-instance DetailProfile section (header kept, one marker line);
      * counters that are N/A or zero in every aggregate;
      * the plan's per-column statistics ("<column>#<id> -> ndv=..."), one marker per run.
    """
    out: list[str] = []
    in_detail = False
    pending: list[Any] = []  # [indent, count, what, purpose] of the lines being omitted

    def flush() -> None:
        if pending:
            indent, count, what, purpose = pending
            out.append(f"{indent}[{count} {what} omitted; use mode='full' for {purpose}]")
            pending.clear()

    def omit(indent: str, what: str, purpose: str) -> None:
        if pending and pending[2] == what:
            pending[1] += 1
        else:
            flush()
            pending[:] = [indent, 1, what, purpose]

    for line in text.splitlines():
        section = _SECTION_RE.match(line)
        column_stats = _COLUMN_STATS_RE.match(line)
        if section:
            flush()
            in_detail = section.group(1) == "DetailProfile"
            out.append(line)
        elif in_detail:
            omit("  ", "lines", "per-instance detail")
        elif column_stats:
            omit(column_stats.group(1), "column-statistics lines", "column statistics")
        elif not _is_empty_counter(line):
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


async def get_query_profile(
    target: FeHttpTarget,
    query_id: str,
    mode: str = "summary",
    max_chars: int = 20000,
    *,
    scope: Scope = "all",
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Profile text of one query; a missing profile is evidence, not an error."""
    qid = (query_id or "").strip().lower()
    if not _QUERY_ID_RE.match(qid):
        return error_response(
            ErrorCode.INVALID_PARAMS,
            "query_id must look like 0123456789abcdef-0123456789abcdef (take it from list_recent_queries)",
        )
    if mode not in ("summary", "full"):
        return error_response(ErrorCode.INVALID_PARAMS, "mode must be 'summary' or 'full'")
    if not 1000 <= max_chars <= 200000:
        return error_response(ErrorCode.INVALID_PARAMS, "max_chars must be between 1000 and 200000")

    evidence: dict[str, Any] = {}
    try:
        text, evidence["v2"] = await _profile_via_v2(target, qid, transport)
        source = "v2"
        if text is None and scope == "all":
            text, evidence["api_text"] = await _profile_via_api_text(target, qid, transport)
            source = "api_text"
    except _FeError as e:
        return error_response(e.code, str(e))

    if text is None:
        return success_response(
            {"query_id": qid, "profile_found": False},
            {"hint": _NOT_FOUND_HINT, "evidence": evidence},
        )

    shown = summarize_profile(text) if mode == "summary" else text
    truncated = len(shown) > max_chars
    if truncated:
        omitted = len(shown) - max_chars
        shown = shown[:max_chars]
    returned_chars = len(shown)
    if truncated:
        shown += f"\n[... truncated: {omitted} more chars; raise max_chars or narrow the question ...]"
    return success_response({
        "query_id": qid,
        "profile_found": True,
        "mode": mode,
        "source": source,
        "total_chars": len(text),
        "returned_chars": returned_chars,
        "truncated": truncated,
        "profile_text": shown,
    })


_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_LIST_DESCRIPTION = (
    "List recently profiled Doris queries, newest first, with their query_id. Only queries "
    "run with profiling on appear: run the SQL through execute_query as "
    "`SELECT /*+SET_VAR(enable_profile=true)*/ ... /* trace:<random token> */`, then call "
    "this tool with sql_contains='<random token>' to get its query_id. Filters: user (exact "
    "Doris user name), sql_contains (case-insensitive substring of the SQL). limit: 1-100."
)
_GET_DESCRIPTION = (
    "Fetch the runtime profile of one Doris query by query_id (from list_recent_queries). "
    "mode='summary' (default) drops the per-instance DetailProfile section, N/A and all-zero "
    "counters and per-column plan statistics, which is usually enough to find the slow "
    "operator; mode='full' returns everything. "
    "Output is capped at max_chars (1000-200000, default 20000) and marked when truncated. "
    "profile_found=false means no profile exists for that id (not run with enable_profile, or evicted)."
)


def register_profile_tools(
    mcp: Any,
    target: FeHttpTarget,
    scope: Scope = "all",
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Register list_recent_queries and get_query_profile on a FastMCP server."""

    def audit(tool: str, params: dict[str, Any], result: str, start: float) -> None:
        err = json.loads(result).get("error") or {}
        log_tool_call(
            tool,
            params=params,
            success=not err,
            duration_ms=(time.monotonic() - start) * 1000,
            error=err.get("message"),
        )

    async def list_recent_queries_tool(limit: int = 20, user: str = "", sql_contains: str = "") -> str:
        start = time.monotonic()
        result = await list_recent_queries(
            target, limit, user, sql_contains, scope=scope, transport=transport
        )
        audit("list_recent_queries", {"limit": limit, "user": user, "sql_contains": sql_contains[:100]}, result, start)
        return result

    async def get_query_profile_tool(
        query_id: str, mode: Literal["summary", "full"] = "summary", max_chars: int = 20000
    ) -> str:
        start = time.monotonic()
        result = await get_query_profile(
            target, query_id, mode, max_chars, scope=scope, transport=transport
        )
        audit("get_query_profile", {"query_id": query_id[:64], "mode": mode, "max_chars": max_chars}, result, start)
        return result

    mcp.tool(list_recent_queries_tool, name="list_recent_queries", description=_LIST_DESCRIPTION, annotations=_READ_ONLY)
    mcp.tool(get_query_profile_tool, name="get_query_profile", description=_GET_DESCRIPTION, annotations=_READ_ONLY)
```

- [ ] **Step 4：运行，确认通过**

```bash
.venv/bin/python -m unittest mcp-server/test/test_agentcore_profile.py
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py'
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3
```
期望：`Ran 29 tests` / `OK`；合计 `Ran 52 tests` / `OK`；`🎉 All tests passed!`。说明：upstream `test_deps.py` 只检查语义层编译路径（`bootstrap.py`、`compiler.py`、`manifest.py`）的 import，不检查新文件；新文件用到的 `httpx`、`mcp` 已在 `pyproject.toml` 锁定（AgentCore 打包只读 `pyproject.toml`），upstream 的 `requirements.txt` 保持原样。

- [ ] **Step 5：收尾**

```bash
bash scripts/check-secrets.sh
git add mcp-server/src/tools/profile.py mcp-server/test/test_agentcore_profile.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(P-05): Doris query-profile tools (list_recent_queries, get_query_profile)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T1.6：P-06 配置 + settings + `build_server`（12 个工具 / Draft 7）

**Files:**
- Create：`mcp-server/config/mcp-server.toml`、`mcp-server/src/agentcore_ext/__init__.py`、`mcp-server/src/agentcore_ext/settings.py`、`mcp-server/src/agentcore_ext/app.py`（本任务只有 `build_server`）
- Test：`mcp-server/test/test_agentcore_settings.py`、`mcp-server/test/test_agentcore_tools.py`

**Interfaces:**
- Consumes：T1.2 `ClusterConfig.fe_http_port`；T1.4 `create_server(config_dir=, config=, service_credentials=, workspace_dir=)`；T1.5 `FeHttpTarget`、`register_profile_tools`
- Produces：
  - `agentcore_ext.settings.SettingsError(RuntimeError)`：消息里从不包含 secret 值
  - `agentcore_ext.settings.Settings`（frozen dataclass）：`doris_host: str, doris_port: int, doris_http_port: int, doris_user: str, doris_password: str (repr=False), profile_scope: str = "all", workspace_dir: str = "", config_dir: str = <mcp-server>/config, mcp_port: int = 8000`
  - `agentcore_ext.settings.load_settings(env: Mapping[str, str] | None = None, secrets_client: Any = None) -> Settings`
  - `agentcore_ext.app.build_server(settings: Settings, *, profile_transport: Any = None) -> FastMCP`
- env 变量（design §5.4）：`DORIS_HOST`（必填）、`DORIS_PORT=9030`、`DORIS_HTTP_PORT=8030`、`DORIS_SECRET_ID`（有值时优先，secret 是 `{"username","password"}` JSON）、`DORIS_USER` / `DORIS_PASSWORD`（仅本地；密码可以为空串但必须设置）、`PROFILE_SCOPE=all|self`、`DORIS_MCP_WORKSPACE_DIR`（默认 `$TMPDIR/doris-mcp-workspace`）、`DORIS_MCP_CONFIG_DIR`（默认 `<mcp-server>/config`）、`MCP_PORT=8000`

- [ ] **Step 1：写失败的测试 `mcp-server/test/test_agentcore_settings.py`**

```python
"""P-06: runtime settings from environment variables / Secrets Manager (src/agentcore_ext/settings.py)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentcore_ext.settings import SettingsError, load_settings  # noqa: E402

PW = "env-s3cret"
SECRET_PW = "sm-s3cret"
BASE = {"DORIS_HOST": "10.0.0.5", "DORIS_USER": "demo_ro", "DORIS_PASSWORD": PW}


class FakeSecrets:
    def __init__(self, secret_string=None, error=None):
        self.secret_string = secret_string
        self.error = error
        self.calls = []

    def get_secret_value(self, SecretId):
        self.calls.append(SecretId)
        if self.error:
            raise self.error
        return {"SecretString": self.secret_string}


def _secret(**doc):
    return FakeSecrets(json.dumps(doc))


class TestLoadSettings(unittest.TestCase):
    def test_env_credentials_and_defaults(self):
        s = load_settings(BASE)
        self.assertEqual((s.doris_host, s.doris_port, s.doris_http_port), ("10.0.0.5", 9030, 8030))
        self.assertEqual((s.doris_user, s.doris_password), ("demo_ro", PW))
        self.assertEqual((s.profile_scope, s.mcp_port), ("all", 8000))
        self.assertEqual(s.workspace_dir, str(Path(tempfile.gettempdir()) / "doris-mcp-workspace"))
        self.assertEqual(Path(s.config_dir), Path(__file__).resolve().parent.parent / "config")

    def test_overrides(self):
        s = load_settings({
            **BASE, "DORIS_PORT": "19030", "DORIS_HTTP_PORT": "18030", "PROFILE_SCOPE": "self",
            "DORIS_MCP_WORKSPACE_DIR": "/tmp/ws", "DORIS_MCP_CONFIG_DIR": "/tmp/cfg", "MCP_PORT": "8080",
        })
        self.assertEqual((s.doris_port, s.doris_http_port, s.profile_scope), (19030, 18030, "self"))
        self.assertEqual((s.workspace_dir, s.config_dir, s.mcp_port), ("/tmp/ws", "/tmp/cfg", 8080))

    def test_empty_env_password_is_allowed(self):
        self.assertEqual(load_settings({**BASE, "DORIS_PASSWORD": ""}).doris_password, "")

    def test_secret_wins_over_env_credentials(self):
        client = _secret(username="mcp_svc", password=SECRET_PW)
        s = load_settings({**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}, secrets_client=client)
        self.assertEqual((s.doris_user, s.doris_password), ("mcp_svc", SECRET_PW))
        self.assertEqual(client.calls, ["doris-mcp/mcp_svc"])

    def test_secret_without_env_credentials(self):
        env = {"DORIS_HOST": "h", "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        s = load_settings(env, secrets_client=_secret(username="mcp_svc", password=SECRET_PW))
        self.assertEqual(s.doris_user, "mcp_svc")

    def test_repr_hides_password(self):
        self.assertNotIn(PW, repr(load_settings(BASE)))


class TestSettingsErrors(unittest.TestCase):
    def assertSettingsError(self, env, fragment, client=None):
        with self.assertRaises(SettingsError) as ctx:
            load_settings(env, secrets_client=client)
        message = str(ctx.exception)
        self.assertIn(fragment, message)
        for secret in (PW, SECRET_PW):
            self.assertNotIn(secret, message)

    def test_missing_host(self):
        self.assertSettingsError({**BASE, "DORIS_HOST": "  "}, "DORIS_HOST is required")

    def test_missing_credentials(self):
        self.assertSettingsError({"DORIS_HOST": "h"}, "set DORIS_SECRET_ID, or DORIS_USER and DORIS_PASSWORD")
        self.assertSettingsError({"DORIS_HOST": "h", "DORIS_USER": "u"}, "DORIS_PASSWORD")

    def test_bad_scope(self):
        self.assertSettingsError({**BASE, "PROFILE_SCOPE": "everyone"}, "PROFILE_SCOPE")

    def test_bad_ports(self):
        self.assertSettingsError({**BASE, "DORIS_PORT": "abc"}, "DORIS_PORT must be an integer")
        self.assertSettingsError({**BASE, "DORIS_HTTP_PORT": "70000"}, "DORIS_HTTP_PORT out of range")
        self.assertSettingsError({**BASE, "MCP_PORT": "0"}, "MCP_PORT out of range")

    def test_secret_not_json_or_missing_keys(self):
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        for client in (FakeSecrets(SECRET_PW), _secret(user="mcp_svc", password=SECRET_PW), FakeSecrets(None)):
            self.assertSettingsError(env, "must be JSON with 'username' and 'password'", client)

    def test_secret_with_empty_values(self):
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        self.assertSettingsError(env, "empty or non-string", _secret(username="mcp_svc", password=""))
        self.assertSettingsError(env, "empty or non-string", _secret(username=7, password=SECRET_PW))

    def test_secret_read_failure_names_only_the_error_type(self):
        env = {**BASE, "DORIS_SECRET_ID": "doris-mcp/mcp_svc"}
        client = FakeSecrets(error=TimeoutError(f"endpoint timeout, password={SECRET_PW}"))
        self.assertSettingsError(env, "cannot read secret doris-mcp/mcp_svc: TimeoutError", client)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2：写失败的测试 `mcp-server/test/test_agentcore_tools.py`**

```python
"""P-01/P-06: build_server() exposes upstream's 10 tools + the 2 profile tools with Quick-safe schemas."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import Client  # noqa: E402

import store.store as st  # noqa: E402
from agentcore_ext.app import build_server  # noqa: E402
from agentcore_ext.settings import load_settings  # noqa: E402
from config.loader import AppConfig  # noqa: E402

UPSTREAM_TOOLS = {
    "get_query_guide", "list_databases", "list_tables", "describe_table", "execute_query",
    "check_service_health", "list_metrics", "list_dimensions_for_metric", "query_metric",
    "reload_semantic_layer",
}
PROFILE_TOOLS = {"list_recent_queries", "get_query_profile"}
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class _BuildCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(st.clear_service_credentials)
        self.workspace = Path(tmp.name) / "ws"
        self.settings = load_settings({
            "DORIS_HOST": "10.9.8.7", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": "svc-pw",
            "DORIS_MCP_WORKSPACE_DIR": str(self.workspace), "DORIS_MCP_CONFIG_DIR": str(CONFIG_DIR),
        })


class TestToolSurface(_BuildCase):
    async def test_exactly_twelve_tools(self):
        mcp = build_server(self.settings)
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
        self.assertEqual(names, UPSTREAM_TOOLS | PROFILE_TOOLS)

    async def test_input_schemas_are_valid_draft7(self):
        # Quick rejects connectors whose tool inputSchema is not valid JSON Schema draft 7.
        mcp = build_server(self.settings)
        async with Client(mcp) as client:
            tools = await client.list_tools()
        for tool in tools:
            with self.subTest(tool=tool.name):
                jsonschema.Draft7Validator.check_schema(tool.inputSchema)
                self.assertEqual(tool.inputSchema.get("type"), "object")
                self.assertTrue(tool.description)

    async def test_no_mcp_auth_and_service_credentials(self):
        mcp = build_server(self.settings)
        self.assertIsNone(mcp.auth)
        self.assertEqual(st.get_effective_credentials(), ("mcp_svc", "svc-pw"))

    async def test_workspace_goes_to_settings_dir(self):
        build_server(self.settings)
        self.assertTrue((self.workspace / "workspaces").is_dir())
        self.assertTrue((self.workspace / "logs").is_dir())

    async def test_invalid_query_id_is_rejected_without_network(self):
        mcp = build_server(self.settings)
        async with Client(mcp) as client:
            result = await client.call_tool("get_query_profile", {"query_id": "../../api/x"}, raise_on_error=False)
        self.assertEqual(json.loads(result.content[0].text)["error"]["code"], "INVALID_PARAMS")


class TestRuntimeConfig(unittest.TestCase):
    def test_config_file_limits(self):
        cc = AppConfig(CONFIG_DIR).cluster
        self.assertEqual((cc.query_timeout, cc.max_rows), (50, 2000))
        self.assertEqual((cc.pool_min_size, cc.pool_max_size, cc.fe_http_port), (0, 5, 8030))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3：运行，确认失败**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_settings.py mcp-server/test/test_agentcore_tools.py`
期望：两个模块都报 `ModuleNotFoundError: No module named 'agentcore_ext'`。

- [ ] **Step 4：写 `mcp-server/config/mcp-server.toml`（P-06）**

```toml
# AgentCore Runtime configuration (P-06). Doris host/ports and credentials come
# from environment variables (src/agentcore_ext/settings.py) and override [server].
[server]
mcp_name = "doris-mcp"
fe_host = "127.0.0.1"
fe_port = 9030
fe_http_port = 8030

[logging]
level = "info"
audit_log = "./logs/audit.log"    # relative to the workspace dir ($TMPDIR/doris-mcp-workspace)
rotation_when = "midnight"
rotation_backup_count = 3

[query]
pool_min_size = 0
pool_max_size = 5                 # one service account; Quick desktop runs <= 20 tools in parallel
pool_idle_timeout_seconds = 300
query_timeout_seconds = 50        # Quick fails any MCP call after 60 s (HTTP 424)
query_max_rows = 2000             # keep results small enough for the agent's context
db_whitelist = []
```

- [ ] **Step 5：写 `mcp-server/src/agentcore_ext/__init__.py`**

```python
"""AgentCore Runtime glue for the Doris MCP server (not part of upstream)."""
```

- [ ] **Step 6：写 `mcp-server/src/agentcore_ext/settings.py`**

```python
"""Runtime settings from environment variables (design §5.4).

DORIS_HOST (required), DORIS_PORT=9030, DORIS_HTTP_PORT=8030
DORIS_SECRET_ID            Secrets Manager secret {"username": ..., "password": ...}; wins over
DORIS_USER / DORIS_PASSWORD  (local runs only)
PROFILE_SCOPE=all|self     self: profile tools only ever see the service account's own profiles
DORIS_MCP_WORKSPACE_DIR    default $TMPDIR/doris-mcp-workspace (the code dir is read-only on AgentCore)
DORIS_MCP_CONFIG_DIR       default <mcp-server>/config
MCP_PORT=8000
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class SettingsError(RuntimeError):
    """Invalid or missing configuration; messages never contain secret values."""


@dataclass(frozen=True)
class Settings:
    doris_host: str
    doris_port: int
    doris_http_port: int
    doris_user: str
    doris_password: str = field(repr=False)
    profile_scope: str = "all"
    workspace_dir: str = ""
    config_dir: str = str(_DEFAULT_CONFIG_DIR)
    mcp_port: int = 8000


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name) or str(default)
    try:
        value = int(raw)
    except ValueError:
        raise SettingsError(f"{name} must be an integer, got {raw!r}") from None
    if not 0 < value < 65536:
        raise SettingsError(f"{name} out of range: {value}")
    return value


def _secrets_client(env: Mapping[str, str]) -> Any:
    import boto3
    from botocore.config import Config

    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
    # Fail fast when the secretsmanager VPC endpoint is missing instead of hanging the cold start.
    config = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"})
    return boto3.client("secretsmanager", region_name=region, config=config)


def _credentials_from_secret(secret_id: str, client: Any) -> tuple[str, str]:
    try:
        raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    except Exception as e:  # noqa: BLE001 - re-raised with context, never with the secret
        raise SettingsError(f"cannot read secret {secret_id}: {type(e).__name__}") from e
    try:
        doc = json.loads(raw)
        user, password = doc["username"], doc["password"]
    except (ValueError, TypeError, KeyError):
        raise SettingsError(f"secret {secret_id} must be JSON with 'username' and 'password'") from None
    if not isinstance(user, str) or not isinstance(password, str) or not user or not password:
        raise SettingsError(f"secret {secret_id} has an empty or non-string username/password")
    return user, password


def load_settings(env: Mapping[str, str] | None = None, secrets_client: Any = None) -> Settings:
    env = os.environ if env is None else env
    host = (env.get("DORIS_HOST") or "").strip()
    if not host:
        raise SettingsError("DORIS_HOST is required")

    secret_id = (env.get("DORIS_SECRET_ID") or "").strip()
    if secret_id:
        user, password = _credentials_from_secret(secret_id, secrets_client or _secrets_client(env))
    else:
        user, password = env.get("DORIS_USER") or "", env.get("DORIS_PASSWORD")
        if not user or password is None:
            raise SettingsError("set DORIS_SECRET_ID, or DORIS_USER and DORIS_PASSWORD")

    scope = env.get("PROFILE_SCOPE") or "all"
    if scope not in ("all", "self"):
        raise SettingsError(f"PROFILE_SCOPE must be 'all' or 'self', got {scope!r}")

    return Settings(
        doris_host=host,
        doris_port=_int(env, "DORIS_PORT", 9030),
        doris_http_port=_int(env, "DORIS_HTTP_PORT", 8030),
        doris_user=user,
        doris_password=password,
        profile_scope=scope,
        workspace_dir=env.get("DORIS_MCP_WORKSPACE_DIR")
        or os.path.join(tempfile.gettempdir(), "doris-mcp-workspace"),
        config_dir=env.get("DORIS_MCP_CONFIG_DIR") or str(_DEFAULT_CONFIG_DIR),
        mcp_port=_int(env, "MCP_PORT", 8000),
    )
```

- [ ] **Step 7：写 `mcp-server/src/agentcore_ext/app.py`（本任务版本：只有 `build_server`，T1.7 会整体替换成完整版）**

```python
"""Assemble the Doris MCP server for AgentCore Runtime (P-01)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from agentcore_ext.settings import Settings
from config.loader import AppConfig
from server import create_server
from tools.profile import FeHttpTarget, register_profile_tools


def build_server(settings: Settings, *, profile_transport: Any = None) -> FastMCP:
    """Upstream server in service mode + the two profile tools."""
    cfg = AppConfig(settings.config_dir)
    cfg.cluster.fe_host = settings.doris_host
    cfg.cluster.fe_mysql_port = settings.doris_port
    cfg.cluster.fe_http_port = settings.doris_http_port

    mcp = create_server(
        config_dir=settings.config_dir,
        config=cfg,
        service_credentials=(settings.doris_user, settings.doris_password),
        workspace_dir=settings.workspace_dir,
    )
    target = FeHttpTarget(
        base_url=f"http://{settings.doris_host}:{settings.doris_http_port}",
        user=settings.doris_user,
        password=settings.doris_password,
    )
    register_profile_tools(mcp, target, scope=settings.profile_scope, transport=profile_transport)
    return mcp
```

- [ ] **Step 8：运行，确认通过**

```bash
.venv/bin/python -m unittest mcp-server/test/test_agentcore_settings.py mcp-server/test/test_agentcore_tools.py
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py'
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3
```
期望：`Ran 19 tests` / `OK`；合计 `Ran 71 tests` / `OK`；`🎉 All tests passed!`。说明：`boto3` 只在 `_secrets_client()` 里按需 import（只有设置了 `DORIS_SECRET_ID` 才会用到），声明在 `pyproject.toml`，不加进 upstream 的 `requirements.txt`。

- [ ] **Step 9：收尾**

```bash
bash scripts/check-secrets.sh
git add mcp-server/config mcp-server/src/agentcore_ext mcp-server/test/test_agentcore_settings.py mcp-server/test/test_agentcore_tools.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(P-01/P-06): runtime settings, config and build_server (12 tools, Draft 7)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T1.7：P-01 `/ping`、stderr 日志、`main`、`mcp_server.py` + HTTP 测试

**Files:**
- Modify：`mcp-server/src/agentcore_ext/app.py`（整体替换为完整版）
- Create：`mcp-server/mcp_server.py`
- Test：`mcp-server/test/test_agentcore_app.py`

**Interfaces:**
- Consumes：T1.6 的 `Settings`、`SettingsError`、`load_settings`、`build_server`
- Produces（`agentcore_ext.app`）：
  - `MCP_PATH = "/mcp"`；`HTTP_MIDDLEWARE = [Middleware(CharsetMiddleware)]`（只挂 upstream 的 `core.charset.CharsetMiddleware`；**不挂** `RequestLoggerMiddleware`——它会把请求 header 和 body（SQL）写到 CloudWatch，而工具调用已经在审计日志里；也不挂 `SessionAffinityProxyMiddleware`——它用于多节点 Web UI 登录，这里用不到）
  - `build_server(...)` 额外注册 `GET /ping` → `{"status": "Healthy", "time_of_last_update": <int>}`，不访问 Doris
  - `configure_logging() -> None`：root logger 和 `doris_new_mcp.audit`（upstream 设了 `propagate=False`）各加一个 stderr handler，可重复调用
  - `main() -> None`：配置错误 → `logger.error("Invalid configuration: …")` + `sys.exit(2)`；否则 `mcp.run(transport="streamable-http", host="0.0.0.0", port=settings.mcp_port, path="/mcp", stateless_http=True, show_banner=False, middleware=HTTP_MIDDLEWARE)`
  - `mcp-server/mcp_server.py`：把 `src/` 放进 `sys.path` 后调用 `main()`（AgentCore Runtime 的 entrypoint）
- FastMCP 3.4.4：`run(**kw)` 会把 `middleware` 传给 `http_app`；SSE 响应不经 CharsetMiddleware 时 content-type 是不带 charset 的 `text/event-stream`，中文会被客户端按 ISO-8859-1 解码

- [ ] **Step 1：写失败的测试 `mcp-server/test/test_agentcore_app.py`**

```python
"""P-01: AgentCore HTTP contract - GET /ping, stateless streamable HTTP on /mcp, stderr logging, main()."""

import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastmcp import FastMCP  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import store.store as st  # noqa: E402
from agentcore_ext import app as app_mod  # noqa: E402
from agentcore_ext.settings import load_settings  # noqa: E402

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _rpc(client, method, params=None, id_=1):
    resp = client.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    if resp.headers["content-type"].startswith("text/event-stream"):
        data = [line[5:].strip() for line in resp.text.splitlines() if line.startswith("data:")]
        return resp, json.loads(data[-1])
    return resp, resp.json()


class _AppCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(st.clear_service_credentials)
        self.env = {
            "DORIS_HOST": "10.9.8.7", "DORIS_USER": "mcp_svc", "DORIS_PASSWORD": "svc-pw",
            "DORIS_MCP_WORKSPACE_DIR": str(Path(tmp.name) / "ws"), "DORIS_MCP_CONFIG_DIR": str(CONFIG_DIR),
        }


class TestHttpContract(_AppCase):
    def client(self):
        mcp = app_mod.build_server(load_settings(self.env))
        http = mcp.http_app(path=app_mod.MCP_PATH, stateless_http=True, middleware=app_mod.HTTP_MIDDLEWARE)
        return TestClient(http)

    def test_ping_is_healthy(self):
        with self.client() as client:
            resp = client.get("/ping")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "Healthy")
        self.assertIsInstance(resp.json()["time_of_last_update"], int)

    def test_initialize_and_list_tools_without_auth(self):
        with self.client() as client:
            resp, init = _rpc(client, "initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn("tools", init["result"]["capabilities"])
            self.assertNotIn("mcp-session-id", {k.lower() for k in resp.headers})
            resp, listed = _rpc(client, "tools/list", id_=2)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(listed["result"]["tools"]), 12)

    def test_sse_responses_declare_utf8(self):
        # Without CharsetMiddleware the header is a bare text/event-stream and
        # clients decode Chinese result text as ISO-8859-1.
        with self.client() as client:
            resp, _ = _rpc(client, "tools/list")
        self.assertEqual(resp.headers["content-type"], "text/event-stream; charset=utf-8")


class TestMain(_AppCase):
    def test_runs_the_agentcore_contract(self):
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(app_mod, "configure_logging"), \
                patch.object(FastMCP, "run") as run:
            app_mod.main()
        kwargs = run.call_args.kwargs
        self.assertEqual(
            {k: kwargs[k] for k in ("transport", "host", "port", "path", "stateless_http")},
            {"transport": "streamable-http", "host": "0.0.0.0", "port": 8000, "path": "/mcp", "stateless_http": True},
        )
        self.assertIs(kwargs["middleware"], app_mod.HTTP_MIDDLEWARE)

    def test_bad_settings_exit_2_with_a_clear_message(self):
        env = {**self.env, "DORIS_PORT": "not-a-port"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(app_mod, "configure_logging"), \
                patch.object(FastMCP, "run") as run, \
                self.assertLogs("doris_new_mcp.agentcore", "ERROR") as logs, \
                self.assertRaises(SystemExit) as exit_:
            app_mod.main()
        self.assertEqual(exit_.exception.code, 2)
        self.assertIn("DORIS_PORT must be an integer", logs.output[0])
        self.assertNotIn("svc-pw", "\n".join(logs.output))
        run.assert_not_called()


class TestConfigureLogging(unittest.TestCase):
    def setUp(self):
        self.loggers = [logging.getLogger(), logging.getLogger("doris_new_mcp.audit")]
        before = {id(lg): list(lg.handlers) for lg in self.loggers}
        level = logging.getLogger().level

        def restore():
            for lg in self.loggers:
                lg.handlers[:] = before[id(lg)]
            logging.getLogger().setLevel(level)

        self.addCleanup(restore)

    def test_root_and_audit_log_to_stderr_once(self):
        app_mod.configure_logging()
        app_mod.configure_logging()
        for lg in self.loggers:
            ours = [h for h in lg.handlers if getattr(h, "_agentcore_stderr", False)]
            self.assertEqual(len(ours), 1, lg.name)
            self.assertIs(ours[0].stream, sys.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2：运行，确认失败**

Run：`.venv/bin/python -m unittest mcp-server/test/test_agentcore_app.py`
期望：`Ran 6 tests`，`FAILED (errors=6)`，都是 `AttributeError: module 'agentcore_ext.app' has no attribute 'MCP_PATH'`（或 `'main'`、`'configure_logging'`）。

- [ ] **Step 3：用完整版覆盖 `mcp-server/src/agentcore_ext/app.py`**

```python
"""Assemble the Doris MCP server for AgentCore Runtime (P-01)."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from agentcore_ext.settings import Settings, SettingsError, load_settings
from config.loader import AppConfig
from core.charset import CharsetMiddleware
from server import create_server
from tools.profile import FeHttpTarget, register_profile_tools

logger = logging.getLogger("doris_new_mcp.agentcore")

MCP_PATH = "/mcp"
# Upstream's RequestLoggerMiddleware is deliberately not mounted: it logs request
# headers and bodies (SQL) to CloudWatch; tool calls are already in the audit log.
# SessionAffinityProxyMiddleware is for multi-node WebUI logins and does not apply.
HTTP_MIDDLEWARE = [Middleware(CharsetMiddleware)]
_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"


def build_server(settings: Settings, *, profile_transport: Any = None) -> FastMCP:
    """Upstream server in service mode + the two profile tools + GET /ping."""
    cfg = AppConfig(settings.config_dir)
    cfg.cluster.fe_host = settings.doris_host
    cfg.cluster.fe_mysql_port = settings.doris_port
    cfg.cluster.fe_http_port = settings.doris_http_port

    mcp = create_server(
        config_dir=settings.config_dir,
        config=cfg,
        service_credentials=(settings.doris_user, settings.doris_password),
        workspace_dir=settings.workspace_dir,
    )
    target = FeHttpTarget(
        base_url=f"http://{settings.doris_host}:{settings.doris_http_port}",
        user=settings.doris_user,
        password=settings.doris_password,
    )
    register_profile_tools(mcp, target, scope=settings.profile_scope, transport=profile_transport)

    @mcp.custom_route("/ping", methods=["GET"])
    async def ping(_: Request) -> JSONResponse:
        # AgentCore Runtime health check; must not touch Doris.
        return JSONResponse({"status": "Healthy", "time_of_last_update": int(time.time())})

    return mcp


def configure_logging() -> None:
    """Send the root and audit loggers to stderr, which AgentCore ships to CloudWatch.

    Upstream writes both only to files under the workspace dir; the audit logger
    does not propagate, so it needs its own handler. Safe to call repeatedly.
    """
    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    for name in ("", "doris_new_mcp.audit"):
        target = logging.getLogger(name)
        if any(getattr(h, "_agentcore_stderr", False) for h in target.handlers):
            continue
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        handler._agentcore_stderr = True  # type: ignore[attr-defined]
        target.addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def main() -> None:
    configure_logging()
    try:
        settings = load_settings()
    except SettingsError as e:
        logger.error("Invalid configuration: %s", e)
        sys.exit(2)
    mcp = build_server(settings)
    logger.info(
        "Doris MCP for AgentCore: Doris %s:%d (http %d) as %s, profile scope %s, workspace %s",
        settings.doris_host, settings.doris_port, settings.doris_http_port,
        settings.doris_user, settings.profile_scope, settings.workspace_dir,
    )
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=settings.mcp_port,
        path=MCP_PATH,
        stateless_http=True,
        show_banner=False,
        middleware=HTTP_MIDDLEWARE,
    )
```

- [ ] **Step 4：写 `mcp-server/mcp_server.py`**

```python
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
```

- [ ] **Step 5：运行，确认通过**

```bash
.venv/bin/python -m unittest mcp-server/test/test_agentcore_app.py
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py'
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline 2>&1 | tail -3
```
期望：`Ran 6 tests` / `OK`；合计 `Ran 77 tests` / `OK`；`🎉 All tests passed!`。

- [ ] **Step 6：真实进程启动冒烟（不连 Doris，只验证入口和退出码）**

```bash
# 1) 配置错误：立即退出，退出码 2，stderr 有原因
env -i PATH="$PATH" DORIS_HOST=127.0.0.1 DORIS_USER=nobody DORIS_PASSWORD=x DORIS_PORT=abc \
  .venv/bin/python mcp-server/mcp_server.py; echo "exit=$?"
# 2) 正常启动：用一个连不上的 Doris 地址，只检查 /ping 和工具数
#    （注意是 `exec env -i … timeout …`：写成 `env -i … exec …` 时 env 会去找名为 exec 的程序，退出码 127）
( exec env -i PATH="$PATH" HOME="$HOME" DORIS_HOST=127.0.0.1 DORIS_PORT=1 DORIS_HTTP_PORT=1 DORIS_USER=nobody DORIS_PASSWORD=x \
    MCP_PORT=18765 DORIS_MCP_WORKSPACE_DIR=/tmp/p1-boot-ws \
    timeout 120 .venv/bin/python mcp-server/mcp_server.py ) > /tmp/p1-boot.log 2>&1 &
for i in $(seq 30); do curl -sf http://127.0.0.1:18765/ping && break; sleep 1; done; echo
.venv/bin/python scripts/mcp_smoke.py --url http://127.0.0.1:18765/mcp list --expect 12 | grep -E "^tools:|FAIL"
pid=$(ss -ltnp | grep ':18765 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); [ -n "$pid" ] && kill "$pid"
grep -E "Doris MCP for AgentCore|service mode" /tmp/p1-boot.log
```
期望：
1. 输出 `[<时间>] ERROR doris_new_mcp.agentcore: Invalid configuration: DORIS_PORT must be an integer, got 'abc'` 和 `exit=2`；
2. `/ping` 返回 `{"status":"Healthy","time_of_last_update":…}`；`tools: 12`；日志里有 `Auth: service mode, MCP auth delegated to the edge; Doris user nobody` 和 `Doris MCP for AgentCore: Doris 127.0.0.1:1 (http 1) as nobody, profile scope all, workspace /tmp/p1-boot-ws`（Doris 连不上也能启动：启动阶段不连 Doris）。

- [ ] **Step 7：收尾**

```bash
bash scripts/check-secrets.sh
git add mcp-server/src/agentcore_ext/app.py mcp-server/mcp_server.py mcp-server/test/test_agentcore_app.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "feat(P-01): AgentCore entrypoint (/ping, stderr logging, stateless streamable HTTP)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task T1.8：本地 E2E（demo_ro → Doris 公网 IP）

**Files:**
- Modify：`scripts/mcp_smoke.py`（新增 `flow` 子命令）
- Modify：`tasks.md`、`progress.md`

**Interfaces:**
- Consumes：T1.7 的 `mcp-server/mcp_server.py`；`credentials.env` 中的 `DORIS_HOST DORIS_MYSQL_PORT DORIS_HTTP_PORT DORIS_RO_USER DORIS_RO_PASSWORD`（只用这 5 个；`DORIS_ROOT_*` 不传给任何进程）
- Produces：`scripts/mcp_smoke.py … flow [--prefix doris___] [--table ecom.fact_order] [--wait 15]`，全部通过时退出码 0；P3 T3.3 / T3.4 经 SigV4 和 Gateway 复用同一个命令
- 前提：本机公网 IP `13.125.9.110` 已在 `doris-demo-sg` 的 9030/8030 白名单里（已有规则，不改）；Doris EC2 在运行（stop/start 后公网 IP 会变，以 `credentials.env` 为准）

- [ ] **Step 1：给 `scripts/mcp_smoke.py` 加 `flow` 子命令**

docstring 的 Examples 里，在 `--stdio` 那一行之后加两行：
```python
  mcp_smoke.py --url http://127.0.0.1:8000/mcp flow                       # profile flow + error cases
  mcp_smoke.py --url "$GW_URL" --bearer-env GW_TOKEN flow --prefix doris___
```

import 区，在 `import os` 之后加：
```python
import secrets
```

找到：
```python
COMMANDS = {"list": cmd_list, "call": cmd_call}
```
替换为：
```python
async def call_json(client: Client, tool: str, params: dict) -> dict:
    payload = result_payload(await client.call_tool(tool, params, raise_on_error=False))
    return payload if isinstance(payload, dict) else {"success": False, "raw": payload}


def error_code(body: dict) -> str | None:
    return (body.get("error") or {}).get("code")


async def cmd_flow(client: Client, args: argparse.Namespace) -> int:
    """Profile flow (design §5.3) + the error cases of the P1 acceptance (design §11)."""
    p = args.prefix
    results: list[bool] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    token = secrets.token_hex(6)
    sql = f"SELECT /*+SET_VAR(enable_profile=true)*/ COUNT(*) AS n FROM {args.table} /* trace:{token} */"
    body = await call_json(client, f"{p}execute_query", {"sql": sql})
    check("execute_query with the profile hint", body.get("success") is True, error_code(body) or "")

    row = None
    deadline = time.monotonic() + args.wait
    while row is None and time.monotonic() < deadline:  # profiles are collected asynchronously
        body = await call_json(client, f"{p}list_recent_queries", {"sql_contains": token, "limit": 5})
        queries = (body.get("data") or {}).get("queries") or []
        row = queries[0] if queries else None
        if row is None:
            await asyncio.sleep(1)
    check("list_recent_queries finds the trace token", row is not None, error_code(body) or "")
    if row is not None:
        print(f"      query_id={row['query_id']} trace_comment_kept={f'trace:{token}' in row['sql']}")
        body = await call_json(client, f"{p}get_query_profile", {"query_id": row["query_id"]})
        data = body.get("data") or {}
        check(
            "get_query_profile summary < 20000 chars",
            data.get("profile_found") is True and data.get("returned_chars", 20000) < 20000,
            f"source={data.get('source')} total_chars={data.get('total_chars')} returned_chars={data.get('returned_chars')}",
        )

    body = await call_json(client, f"{p}get_query_profile", {"query_id": "../../api/x"})
    check("invalid query_id -> INVALID_PARAMS", error_code(body) == "INVALID_PARAMS")
    body = await call_json(client, f"{p}get_query_profile", {"query_id": "ffffffffffffffff-ffffffffffffffff"})
    check("unknown query_id -> profile_found=false",
          body.get("success") is True and (body.get("data") or {}).get("profile_found") is False)
    body = await call_json(client, f"{p}execute_query", {"sql": f"DELETE FROM {args.table} WHERE 1 = 0"})
    check("DML is rejected", body.get("success") is False, error_code(body) or "")
    print(f"flow: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


COMMANDS = {"list": cmd_list, "call": cmd_call, "flow": cmd_flow}
```

`main()` 里，找到 `p_call.add_argument("params", …)` 这一行，在它之后加：
```python
    p_flow = sub.add_parser("flow", help="profile flow + error cases against a Doris MCP")
    p_flow.add_argument("--prefix", default="", help="tool name prefix, e.g. doris___ through the Gateway")
    p_flow.add_argument("--table", default="ecom.fact_order", help="table the profiled COUNT(*) reads")
    p_flow.add_argument("--wait", type=float, default=15.0, help="seconds to wait for the profile to appear")
```

检查：`.venv/bin/python scripts/mcp_smoke.py flow --help` 能列出 `--prefix --table --wait`。
说明：`DELETE … WHERE 1 = 0` 会被 MCP 的 SQL 校验器在发往 Doris 之前拦下（`INVALID_SQL`），即使漏过，`demo_ro` 也没有写权限，且 `WHERE 1 = 0` 不匹配任何行。

- [ ] **Step 2：用 demo_ro 启动 server（端口 8000）**

```bash
CRED=/home/ubuntu/AI-code/Doris-test/credentials.env
( source "$CRED"          # 文件里没有 export：变量只在这个子 shell 里，下面只 export 需要的
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_HTTP_PORT="${DORIS_HTTP_PORT:-8030}"
  export DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD="$DORIS_RO_PASSWORD"
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_PASSWORD
  export MCP_PORT=8000 DORIS_MCP_WORKSPACE_DIR=/tmp/p1-e2e-ws
  exec timeout 900 .venv/bin/python mcp-server/mcp_server.py ) > /tmp/p1-e2e.log 2>&1 &
for i in $(seq 30); do curl -sf http://127.0.0.1:8000/ping && break; sleep 1; done; echo
```
期望：打印 `{"status":"Healthy",…}`。`timeout 900` 是保险：会话中断时 server 15 分钟后自己退出。

- [ ] **Step 3：12 个工具 + 健康检查**

```bash
URL=http://127.0.0.1:8000/mcp
.venv/bin/python scripts/mcp_smoke.py --url $URL list --expect 12
.venv/bin/python scripts/mcp_smoke.py --url $URL call check_service_health | grep -E '"(success|doris|doris_error)"'
.venv/bin/python scripts/mcp_smoke.py --url $URL call list_databases | grep -c '"ecom"'
```
期望：`tools: 12`，12 个名字与 R-20 一致，两个 profile 工具带 `[readOnly]`；健康检查 `"success": true` 和 `"doris": "connected"`（没有 `doris_error`）；`list_databases` 的计数 ≥ 1。

- [ ] **Step 4：profile flow + 错误情况**

```bash
.venv/bin/python scripts/mcp_smoke.py --url $URL flow; echo "exit=$?"
```
期望（spec 阶段实测值供对照；首行 `connected+initialized in … ms`、末行 `total … ms` 省略）：
```
  [PASS] execute_query with the profile hint
  [PASS] list_recent_queries finds the trace token
      query_id=<32 hex>-… trace_comment_kept=True
  [PASS] get_query_profile summary < 20000 chars  (source=v2 total_chars≈103000 returned_chars≈9100)
  [PASS] invalid query_id -> INVALID_PARAMS
  [PASS] unknown query_id -> profile_found=false
  [PASS] DML is rejected  (INVALID_SQL)
flow: 6/6 passed
exit=0
```
把 `source`、`total_chars`、`returned_chars`、`trace_comment_kept` 记进 progress。`trace_comment_kept=False` 时（Doris 升级后剥掉了注释），在 progress 记录并改用 design §5.3 的备选写法 `SELECT '<token>' AS _trace, …`。

- [ ] **Step 5：错误密码（第二个实例，端口 8001）**

```bash
( source "$CRED"
  export DORIS_HOST DORIS_PORT="${DORIS_MYSQL_PORT:-9030}" DORIS_HTTP_PORT="${DORIS_HTTP_PORT:-8030}"
  export DORIS_USER="$DORIS_RO_USER" DORIS_PASSWORD=wrong-on-purpose
  unset DORIS_ROOT_USER DORIS_ROOT_PASSWORD DORIS_RO_PASSWORD
  export MCP_PORT=8001 DORIS_MCP_WORKSPACE_DIR=/tmp/p1-e2e-ws-bad
  exec timeout 300 .venv/bin/python mcp-server/mcp_server.py ) > /tmp/p1-e2e-bad.log 2>&1 &
for i in $(seq 30); do curl -sf http://127.0.0.1:8001/ping >/dev/null && break; sleep 1; done
BAD=http://127.0.0.1:8001/mcp
KEYS='"(success|doris|doris_error|code|message)"'
.venv/bin/python scripts/mcp_smoke.py --url $BAD call list_recent_queries | grep -E "$KEYS"
.venv/bin/python scripts/mcp_smoke.py --url $BAD call check_service_health | grep -E "$KEYS"
.venv/bin/python scripts/mcp_smoke.py --url $BAD call list_databases | grep -E "$KEYS"
```
期望：
- `list_recent_queries` → `"success": false`，`"code": "UNAUTHENTICATED"`（FE HTTP 返回 body `code:401`）；
- `check_service_health` → `"success": true`，`"doris": "unavailable"`，`"doris_error": "credentials rejected by Doris"`；
- `list_databases` → `"success": false`，`"code": "CONNECTION_ERROR"`，消息含 `Access denied`（MySQL 1045）；消息里只有用户名，没有密码；
- 进程不退出、MCP 连接不断开。每个工具只调用一次，避免触发账号锁定策略。

- [ ] **Step 6：日志检查（密码零命中 + 审计日志）**

```bash
( source "$CRED"
  for f in /tmp/p1-e2e.log /tmp/p1-e2e-bad.log /tmp/p1-e2e-ws/logs/*.log /tmp/p1-e2e-ws-bad/logs/*.log; do
    printf '%s: ' "$f"; printf '%s\n' "$DORIS_RO_PASSWORD" | grep -cF -f - "$f"
  done )
wc -l /tmp/p1-e2e-ws/logs/audit.log
grep -c "doris_new_mcp.audit" /tmp/p1-e2e.log
```
期望：每个文件都是 `: 0`（密码通过管道交给 grep，不出现在命令行参数里）；`audit.log` 有十几行（每次工具调用一行）；stderr 日志里也有同样数量级的 `doris_new_mcp.audit` 行（P3 进 CloudWatch 靠的就是这一份）。

- [ ] **Step 7：停止 server，清理临时目录**

```bash
for p in 8000 8001; do
  pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | cut -d= -f2)
  [ -n "$pid" ] && kill "$pid"
done
sleep 1; ss -ltn | grep -E ':(8000|8001) ' || echo "stopped"
rm -rf /tmp/p1-e2e-ws /tmp/p1-e2e-ws-bad /tmp/p1-boot-ws
```
期望：`stopped`。日志文件 `/tmp/p1-e2e*.log` 留着备查（不进仓库）。

- [ ] **Step 8：收尾**

勾选 T1.8；progress「当前状态」写 P1 完成、下一步（P2 需要先编写 `plans/P2-doris.md`），日志记录 Step 3–6 的实测数字和 3 种错误的实际返回码。

```bash
bash scripts/check-secrets.sh
git add scripts/mcp_smoke.py specs/doris-mcp-quick/tasks.md specs/doris-mcp-quick/progress.md
git commit -m "test(p1): T1.8 local E2E against Doris as demo_ro (12 tools, profile flow, error cases)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## P1 完成标准（对照 design §11）

- [x] `tools/list` 恰好 12 个，Draft 7 校验通过（T1.6、T1.7、T1.8 Step 3）
- [x] upstream 离线测试全部通过；`test_agentcore_*.py` 共 77 个测试全部通过
- [x] profile：hint 执行 → `list_recent_queries` 能找到 → summary < 20 000 字符（T1.8 Step 4）
- [x] 非法 qid → `INVALID_PARAMS`；找不到 → `profile_found=false`；密码错误 → `UNAUTHENTICATED` / `unavailable` / `CONNECTION_ERROR`（T1.8 Step 4–5）
- [x] 所有日志里真实密码命中数为 0（T1.8 Step 6）
- [x] `git log --oneline -- mcp-server` 能看到：vendoring、P-02、P-03、P-04、P-05、P-01/P-06、P-01 共 7 个 commit
