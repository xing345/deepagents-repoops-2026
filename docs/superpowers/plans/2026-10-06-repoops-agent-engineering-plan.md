# RepoOps Agent 工程化改造计划

## 目标

在不改变 `libs/deepagents` 核心 SDK 行为的前提下，新增一个独立的 `apps/repoops` 应用包，形成可验证的代码仓库 Agent 工程骨架。第一阶段覆盖：

- B：代码仓库混合检索（SQLite FTS5 + 可插拔向量检索）
- C：任务状态、检查点与恢复
- E：策略控制的工作区与命令执行
- G：离线评测流水线
- H：结构化观测、耗时与 token/cost 统计接口
- I：测试套件与 CI 配置

## 约束

- 不在核心 SDK 中加入产品级 API、UI 或仓库业务逻辑。
- 默认测试不依赖 Anthropic/OpenAI API Key，不访问外网。
- 执行器只接受参数数组，不使用 `shell=True`；工作区边界、命令白名单、超时和输出上限由策略统一控制。
- “工作区隔离”第一阶段是策略控制的进程级边界，不宣称等同于 Docker/操作系统级沙箱。
- 生产实现先写失败测试，再补最小实现；每个模块完成后运行针对性测试，再运行全量离线测试。

## 实施顺序

### 1. 应用包骨架与测试基础设施

文件：

- `apps/repoops/pyproject.toml`
- `apps/repoops/src/repoops/__init__.py`
- `apps/repoops/tests/conftest.py`
- `apps/repoops/.gitignore`

验收：可以通过 `uv sync` 创建独立环境，并运行 pytest。

### 2. B：混合代码检索

文件：

- `apps/repoops/src/repoops/retrieval/models.py`
- `apps/repoops/src/repoops/retrieval/chunker.py`
- `apps/repoops/src/repoops/retrieval/index.py`
- `apps/repoops/tests/retrieval/test_chunker.py`
- `apps/repoops/tests/retrieval/test_hybrid_retriever.py`

验收：索引 Python/Markdown 等文本文件；同时执行 FTS5 关键词检索和向量相似度检索；以可配置权重融合；结果包含路径、行号、分数和片段；索引可重复构建。

### 3. C：任务检查点与恢复

文件：

- `apps/repoops/src/repoops/runtime/models.py`
- `apps/repoops/src/repoops/runtime/task_store.py`
- `apps/repoops/src/repoops/runtime/checkpoints.py`
- `apps/repoops/tests/runtime/test_task_store.py`
- `apps/repoops/tests/runtime/test_checkpoints.py`

验收：任务状态只能按合法状态机迁移；每个步骤写入可序列化检查点；进程重启后可读取最近检查点；重复恢复不会重复完成已提交步骤。

### 4. E：工作区与安全执行策略

文件：

- `apps/repoops/src/repoops/security/policy.py`
- `apps/repoops/src/repoops/security/executor.py`
- `apps/repoops/tests/security/test_policy.py`
- `apps/repoops/tests/security/test_executor.py`

验收：拒绝工作区外路径、未允许的可执行文件、shell 字符串命令和超时配置；允许的命令以 `shell=False` 执行；输出超过上限时截断并标记；策略错误可解释。

### 5. G：离线评测流水线

文件：

- `apps/repoops/src/repoops/evaluation/models.py`
- `apps/repoops/src/repoops/evaluation/runner.py`
- `apps/repoops/tests/evaluation/test_runner.py`
- `apps/repoops/evaluation/datasets/retrieval_smoke.jsonl`

验收：从 JSONL 读取样例，运行检索评测，计算 recall@k、MRR、平均延迟和失败数，输出机器可读报告；不需要模型 API。

### 6. H：观测与成本统计

文件：

- `apps/repoops/src/repoops/observability/events.py`
- `apps/repoops/src/repoops/observability/telemetry.py`
- `apps/repoops/tests/observability/test_telemetry.py`

验收：每次任务/工具/检索调用都有 run_id、task_id、事件类型、耗时和状态；token/cost 字段可选但结构稳定；日志 JSONL 可回放和聚合。

### 7. 应用编排与 CI

文件：

- `apps/repoops/src/repoops/application.py`
- `apps/repoops/src/repoops/agent_factory.py`
- `apps/repoops/tests/test_application.py`
- `apps/repoops/tests/agent/test_factory.py`
- `.github/workflows/repoops-tests.yml`
- `apps/repoops/README.md`

验收：组件可以组合成一个离线可运行的 RepoOps 工作流；CI 仅执行离线测试、ruff 和类型检查；README 明确安全边界、启动方式和后续接入 Deep Agents 模型的位置。

## 最终验证

在 `apps/repoops` 中依次执行：

```powershell
uv run pytest -q
uv run ruff check .
uv run ty check src --extra-search-path ../../libs/deepagents
```

并单独复跑 `libs/deepagents` 的离线单元测试，确认新增应用没有修改 SDK 行为。
