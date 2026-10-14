# RepoOps Agent

面向代码仓库的工程化 Agent 应用层，构建在本仓库的 `deepagents` SDK 之上，第一阶段聚焦可验证的基础设施：

- 混合代码检索：SQLite FTS5 关键词召回 + 可插拔向量提供器
- 任务恢复：SQLite 状态机、步骤检查点和幂等恢复
- 安全执行：工作区边界、可执行文件白名单、环境变量过滤、超时和输出上限
- 离线评测：JSONL 数据集、recall@k、MRR、延迟和失败样例
- 运行观测：JSONL 事件、span 计时、token/cost 汇总

## 本地运行

```powershell
cd apps/repoops
uv sync
uv run pytest -q
uv run ruff check .
uv run ty check src --extra-search-path ../../libs/deepagents
```

默认测试不需要 Anthropic/OpenAI API Key，也不会访问外网。

## 架构边界

`RepoOpsApplication` 是离线应用编排入口。它把检索、任务存储、检查点、安全执行和 telemetry 组合起来；`libs/deepagents` 仍保持通用 SDK 职责，不放入仓库业务逻辑、产品 API 或 UI。

当前执行器是“策略控制的进程级工作区边界”，不是 Docker 或操作系统级沙箱。生产环境仍应在容器、微虚拟机或远程 sandbox 中运行不可信代码。

`agent_factory.py` 已提供 `create_repoops_agent()`：它用 `create_deep_agent()` 注册检索和安全执行工具，并把 `task_id` 作为任务/检查点/telemetry 的关联键；模型调用仍无法绕过本目录的执行策略。

## 评测样例

离线检索样例位于 `evaluation/datasets/retrieval_smoke.jsonl`。它只依赖本地仓库文本和确定性的 hash 向量器，便于在 CI 中做回归基线；生产环境可替换为真实 embedding provider，而无需修改索引和评测接口。
