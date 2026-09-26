# Spec：doris-mcp-quick

把 upstream `velodb-mcp-server` 改造后部署到 **Amazon Bedrock AgentCore Runtime**，通过 **AgentCore Gateway** 接入 **Amazon Quick 桌面版**，在真实 Doris 电商演示库上演示语义层问答、业务排查、profile 诊断和建表评审。

## 文件说明

| 文件 | 内容 | 什么时候更新 |
|---|---|---|
| `requirements.md` | 需求 R-xx（EARS 句式 + 验收标准），已定决策 D1–D8 | 需求或决策变化时（要记录原因）|
| `design.md` | 架构、已核实事实、补丁设计、基础设施、Quick 集成、风险 | 阶段结论推翻或补充设计时（在文首变更记录中写明）|
| `tasks.md` | P0–P5 总任务清单，每个任务标注执行方和对应需求 | 任务完成时勾选；新增或拆分任务 |
| `plans/Px-*.md` | 某阶段逐步执行的计划（含代码、命令、预期输出）| **及时编写**：开始该阶段前写好并经用户 review |
| `progress.md` | 顶部是「当前状态」，下面是追加式日志 | **每个任务结束时都要更新** |

## 任务标签

- `[AI]`：Claude 直接执行（只改本地文件，或只做只读查询）。
- `[AI+GATE]`：Claude 先准备好命令并 dry-run，**用户确认后**才执行（涉及 AWS 资源、Doris 账号或安全组）。
- `[USER]`：只能由用户操作（Quick 桌面版 UI、笔记本上的 AWS 凭证等），Claude 提供步骤和材料。

## 为什么这样组织

- **断线可恢复**：状态全部在仓库文件和 git 里，不依赖会话记忆。仓库根目录的 `CLAUDE.md` 会自动加载，里面有恢复协议。
- **需求可追溯**：tasks → R-xx → 验收标准；design 里的每条事实都标了来源（✅ 实测 / 📄 文档 / ❓ 待验证）。
- **计划及时编写**：P0/P1 已有详细计划；P2–P5 依赖前一阶段的结论，等到开始时再写，避免写了又推翻。
