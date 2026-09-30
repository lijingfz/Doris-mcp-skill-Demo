# 如何继续（给人看的操作指南）

> 这个文件告诉**你**下次打开项目时怎么做；Claude 的恢复协议在 `CLAUDE.md` 里。
> 进度不写在这里：当前做到哪一步，以 `specs/doris-mcp-quick/progress.md` 顶部的「当前状态」为准。

## 一句话版

```bash
tmux new -A -s doris
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo && claude
```

然后对 Claude 说「继续」，并在同一句话里附上你要做的决定（见第 2 步）。

---

## 1. 启动

```bash
tmux new -A -s doris                        # 可选但推荐：SSH 断线后 Claude Code 不会退出
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
claude                                      # 开新会话（推荐）
```

- **必须在仓库根目录启动**。只有这样才会自动加载 `CLAUDE.md`（恢复协议和硬性规则）；会话历史也是按目录保存的。
- 其他启动方式：
  - `claude --continue`：接上最近一次对话。
  - `claude --resume`：从历史会话里挑一个。

  这两种只是图方便，不用也不会丢进度。上下文已经很长时，开新会话反而更干净。
- tmux 断线后，重新 SSH 登录，再执行一次 `tmux new -A -s doris` 就能回到原来的界面。
- 退出前不需要额外操作：每个任务完成时都会提交 commit。

## 2. 第一句话怎么说

先看 `progress.md` 里「阻塞」一行写的是什么，再选对应的说法：

| 当前情况 | 第一句话示例 |
|---|---|
| 阻塞 =「等待用户 review」，你已经看完计划 | `继续。计划 review 通过。P1 用 subagent-driven，P0 用 native，先做 P1。` |
| 看完计划，有修改意见 | `继续。先按以下意见修改 plans/P1-mcp-server.md：…… 修改完再给我看。` |
| 任务执行到一半断线了 | `继续` |
| Claude 上次停在某个 GATE，正在等你确认 | `继续。T0.2 的 dry-run 我看过了，确认执行。`（Claude 会先重新跑一次 dry-run 给你看，再执行）|
| 只想了解进度，不执行 | `汇报一下当前进度和下一步，先不要执行。` |

### 两种执行方式

| 方式 | 做法 | 适合 |
|---|---|---|
| **subagent-driven** | 每个任务交给一个新的子代理实现，再由另一个子代理审查，最后整体审查一次 | P1：纯本地代码，任务之间接口依赖紧，一个补丁出错会连带后面 |
| **native** | Claude 在当前会话里逐个任务执行，最后整体审查一次 | P0：多个 GATE 需要你逐个确认，一问一答地推进更顺 |

P1 不依赖 P0，可以先做，也可以和 P0 并行。

## 3. Claude 会自动做什么

按 `CLAUDE.md` 的恢复协议：

1. 读 `progress.md` 的「当前状态」。
2. 在 `tasks.md` 中找到第一个未勾选的任务，打开它对应的 `plans/*.md` 章节。
3. 运行 `git status` 和 `git log`。有未提交的改动时，先判断属于哪个任务；判断不了就问你，**不会丢弃改动**。
4. 执行 `source infra/state.env`，拿到已创建的 AWS 资源 ID。
5. 继续执行。每完成一个任务：勾选 tasks.md → 更新 progress.md → 运行 `scripts/check-secrets.sh` → commit（不 push）。

## 4. 需要你本人参与的地方

- **GATE 确认**：凡是创建或修改 AWS 资源、Doris 账号或权限、安全组的操作，Claude 都会先给你看 dry-run，确认后才执行 `APPLY=1`。一次确认只对应一次操作。
- **取 secret**：Cognito client secret、演示用户密码、Gateway token 等，要在**你自己的另一个终端**里执行命令获取，**不要用 Claude Code 的 `!` 前缀**，否则 secret 会进入对话记录。计划里标了「（用户）」的步骤都属于这一类。
- **`[USER]` 任务**：Quick 桌面版界面上的操作（连接器、Agent、Skills、彩排）。Claude 提供步骤和材料，由你来操作，然后把结果告诉 Claude。

## 5. 自己查看进度

```bash
cd /home/ubuntu/AI-code/Doris-mcp-skill-Demo
sed -n '/## 当前状态/,/## 日志/p' specs/doris-mcp-quick/progress.md    # 当前阶段 / 下一步 / 阻塞
grep -n '\[ \]' specs/doris-mcp-quick/tasks.md | head -5                  # 接下来的任务
git log --oneline | head -15                                              # 已完成的提交
git status --short                                                        # 有没有未提交的改动
cat infra/state.env                                                       # 已创建的 AWS 资源 ID（不含 secret）
```

## 6. 常见情况

| 情况 | 怎么办 |
|---|---|
| `/tmp` 下的临时文件不见了（机器重启过）| 不影响。每个阶段的完整代码都嵌在 `plans/*.md` 里；说「继续」，Claude 会先按计划的「从计划取文件」一节把工具和文件重新取出来 |
| 演示当天 | 按 `quick/runbook.md` 执行：演示前 30 分钟内让 Claude 跑 `scripts/demo-check.sh pre`（约 1.5 分钟），结束后跑 `post`。AWS 资源按用户决定保留（2026-09-30）；以后要清理时由用户自己执行 `infra/99-cleanup.sh`（先 dry-run，见 `README.md` 第 9 节），Claude 做只读核对和记录 |
| `git status` 显示有未提交的改动 | 直接说「继续」。Claude 会对照 progress.md 判断归属；判断不了会问你 |
| GATE 执行到一半断线 | 说「继续」。`infra/*.sh` 可以重复执行，已经存在的资源会跳过；Claude 会先 dry-run，让你确认还剩哪些操作 |
| 想修改需求或决策 | 直接告诉 Claude。它会先改 `requirements.md` / `design.md`（写明变更原因），再调整计划 |
| 想推送到远程仓库 | 远程是私有仓库 `lijingfz/Doris-mcp-skill-Demo`（D8，P2 起推送过）。每次推送都要你明确确认；Claude 不会自己推送，也不会强推 |
| 想换 commit 作者（当前是仓库内配置的 `ubuntu@主机名`）| 先执行 `git config user.name "…"` 和 `git config user.email "…"`；如果还要改写已有提交的作者，再执行 `git rebase -r --root --exec 'git commit --amend --no-edit --reset-author'` |

## 文件地图

| 文件 | 作用 |
|---|---|
| `README.md` | 项目说明：架构、用法、工作原理、测试原理、资源保留与清理（第一次看这个仓库、或隔一段时间回来时先读）|
| `RESUME.md` | 本文：人怎么继续 |
| `CLAUDE.md` | Claude 怎么继续（恢复协议）+ 硬性规则 |
| `specs/doris-mcp-quick/progress.md` | **当前状态** + 日志 |
| `specs/doris-mcp-quick/tasks.md` | 总任务清单（P0–P5）|
| `specs/doris-mcp-quick/plans/` | 分阶段的详细计划（P0–P5 已写好）|
| `specs/doris-mcp-quick/requirements.md` / `design.md` | 需求与设计 |
| `quick/runbook.md` | 演示手册：演示前的检查、设置、演示流程、出问题时怎么办、演示后、每步耗时（P5 写好）|
