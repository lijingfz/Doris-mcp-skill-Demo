# Doris MCP on AgentCore × Amazon Quick 桌面版

本仓库按 **spec 驱动**推进：需求、设计、任务、进度都落在 `specs/doris-mcp-quick/`，每完成一个任务就提交一次 git。
会话中断后，新会话只要按下面的「恢复协议」执行，就能从断点继续。

## 恢复协议（每次新会话先做）

1. 读 `specs/doris-mcp-quick/progress.md` 顶部的「当前状态」块：当前阶段、进行中的任务、下一步、阻塞项。
2. 读 `specs/doris-mcp-quick/tasks.md`，找到第一个未勾选的任务，打开它链接的 `plans/*.md` 中对应的 Task。
3. `git status` + `git log --oneline -15`。如果有未提交的改动，先对照 progress.md 判断属于哪个任务：能续就续，不确定就问用户。**不要 reset / checkout 丢弃改动。**
4. `source infra/state.env`，拿到已创建的 AWS 资源 ID（该文件只有非敏感 ID）。
5. 继续执行。每完成一个任务：勾选 tasks.md → 更新 progress.md（「当前状态」+ 在日志末尾追加一条）→ 提交 commit（改动和进度一起提交）。

用户在新会话里说「继续」即可触发以上流程。

## 硬性规则

- **GATE**：任何创建或修改 AWS 资源、修改 Doris 账号/权限、修改安全组的操作，先展示将要执行的命令（`infra/*.sh` 默认是 dry-run），用户确认后才用 `APPLY=1` 执行。一次确认只对应那一次操作。
- 安全组不允许出现 `0.0.0.0/0`；新增规则只用 SG 引用或 `/32`。`doris-demo-sg` 现有的 `13.125.9.110/32` 规则不动。
- 密码和 secret 不能出现在仓库、命令行参数、日志或对话输出里。Doris 凭证只在 `/home/ubuntu/AI-code/Doris-test/credentials.env`（项目外），用 `set -a; source …; set +a` 加载，**永远不要 echo 或 cat 这个文件**。AWS 侧凭证放 Secrets Manager。
- 提交前运行 `scripts/check-secrets.sh`，有命中就不能提交。
- `demo_ro` 是只读账号；MCP 不执行任何 DDL/DML（写操作由人工执行）。
- 不要修改 `prepare/`（原始材料）。
- commit 只在当前任务的计划要求提交时才做；commit message 结尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。不 push（D8：是否推送由用户决定）。
- 对用户用中文；代码、代码注释、工具描述用英文（与 upstream 一致）。

## 关键路径

| 路径 | 作用 |
|---|---|
| `specs/doris-mcp-quick/requirements.md` | 需求（R-xx）+ 已定决策 D1–D8 |
| `specs/doris-mcp-quick/design.md` | 设计（由 `docs/改造方案.md` v0.1 演进而来，v0.1 原稿见 git 历史第一个提交）|
| `specs/doris-mcp-quick/tasks.md` | 总任务清单（P0–P5），标注执行方与 GATE |
| `specs/doris-mcp-quick/plans/` | 分阶段的详细执行计划（按需及时编写）|
| `specs/doris-mcp-quick/progress.md` | 当前状态 + 追加式日志 |
| `infra/` | 幂等 AWS CLI 脚本（默认 dry-run）+ `state.env` 资源清单 |
| `mcp-server/` | vendored upstream + 补丁 = AgentCore codeLocation |
| `dorismcp/` | agentcore CLI 项目（`agentcore/agentcore.json`）|
| `.venv/` | 本地开发 venv（放在 codeLocation 之外，避免被打进 CodeZip）|

## 常用命令

```bash
tmux new -A -s doris                      # 在 tmux 里跑 Claude Code，SSH 断线不丢会话
claude --continue                         # 恢复最近一次会话（spec 仍是权威状态）
bash infra/10-network.sh                  # dry-run：只打印将要执行的命令
APPLY=1 bash infra/10-network.sh          # 用户确认后才执行
PYTHON_BIN=$PWD/.venv/bin/python bash mcp-server/test/run_all_tests.sh --offline
.venv/bin/python -m unittest discover -s mcp-server/test -p 'test_agentcore_*.py' -v
bash scripts/check-secrets.sh             # 提交前检查是否有明文密码
```
