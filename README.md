# GitHub Agent Lab

本仓库是一个本地运行的实验项目，用来探索“基于 LLM 的 GitHub 开源贡献自动化 agent”。

## 项目目标

- 读取 GitHub 仓库信息
- 分析潜在可贡献点
- 生成修改计划或 patch
- 本地验证修改
- 产出 PR draft

## 当前阶段做什么

- 初始化一个干净、可持续迭代的 Python 仓库
- 提供一个可运行的 CLI 最小骨架
- 预留 agents、workflows、prompts、playground 目录
- 提供最基础测试与配置模板

## 当前阶段不做什么

- 不实现完整业务流程
- 不做前端、部署、多用户系统
- 不做 auto-merge、自动 reviewer 分配、自动 issue/comment 发布

## 目录结构

```text
github-agent-lab/
  README.md
  .gitignore
  pyproject.toml
  .env.example
  src/
    main.py
    cli.py
    config.py
    llm_client.py
    github_client.py
    repo_manager.py
    agents/
      __init__.py
      scout.py
      planner.py
      coder.py
      validator.py
      pr_writer.py
    workflows/
      __init__.py
      analyze_repo.py
      generate_patch.py
      validate_patch.py
  prompts/
    scout.md
    planner.md
    coder.md
    validator.md
    pr_writer.md
  playground/
    repos/
    outputs/
    logs/
  tests/
    test_smoke.py
```

## 本地运行

1. 创建并激活 Python 3.11+ 虚拟环境
2. 安装依赖

```bash
pip install -e ".[dev]"
```

3. 查看 CLI 帮助

```bash
python -m src.main --help
```

4. 运行占位 analyze 命令

```bash
python -m src.main analyze https://github.com/owner/repo
```

5. 运行测试

```bash
pytest -q
```

6. 显式执行 publish（不会在 run-task 中自动触发）

```bash
python -m src.main publish https://github.com/owner/repo --branch feature/repo-task-001 --draft-pr
```

## Publish 闭环

publish 命令会在本地工作流产物基础上执行最小发布闭环：

- 创建/切换功能分支
- `git add` + `git commit`
- `git push` 到远端
- 创建 draft PR
- 落盘 `playground/outputs/publish_result.json`

安全边界：

- 必须显式执行 `publish`，不会在 `run-task` 中隐式发布
- 默认保护 `main/master`，禁止直接发布到受保护分支
- publish 失败时会保留本地提交结果并输出清晰错误，不做自动 merge

运行 llm_integration 测试前必须提供真实 LLM 环境变量：

```bash
set LLM_API_KEY=your_real_key
set LLM_BASE_URL=your_real_base_url
set LLM_MODEL=your_real_model
set LLM_TIMEOUT_SECONDS=120
set LLM_MAX_RETRIES=1
set LLM_RETRY_BACKOFF_BASE_SECONDS=1.0
set LLM_USE_STREAM=1
```

默认回归测试不依赖真实 LLM 环境变量。

运行真实 LLM 集成测试：

```bash
set RUN_LLM_INTEGRATION=1
pytest -q -m llm_integration -o addopts=""
```

运行一次真正的端到端 LLM 集成测试（run-task 多步骤编排）：

```bash
set RUN_LLM_INTEGRATION=1
set LLM_API_KEY=your_real_key
set LLM_BASE_URL=your_real_base_url
set LLM_MODEL=your_real_model
set LLM_TIMEOUT_SECONDS=120
set LLM_MAX_RETRIES=1
set LLM_RETRY_BACKOFF_BASE_SECONDS=1.0
set LLM_USE_STREAM=1
pytest -q -m llm_integration -o addopts="" tests/test_llm_integration.py -k run_task
```

说明：
- 上述命令会执行 `run-task` 并开启 `--use-llm-discover`、`--use-llm-plan`、`--use-llm-patch`、`--use-llm-apply`、`--use-llm-validate`、`--use-llm-pr-draft`。
- 建议在网络稳定、配额充足时运行，以减少因外部服务导致的波动。

建议做一次超时对照（120 vs 180）：

```bash
set LLM_TIMEOUT_SECONDS=120
pytest -q -m llm_integration -o addopts="" tests/test_llm_integration.py -k run_task

set LLM_TIMEOUT_SECONDS=180
pytest -q -m llm_integration -o addopts="" tests/test_llm_integration.py -k run_task
```

对照时重点查看 `playground/outputs/run_task_result.json` 中的 `llm_steps_used` 与 `llm_steps_fallback`。

说明：
- 默认 `pytest -q` 通过 `llm_integration` marker 隔离真实 LLM 测试。
- 集成测试命令通过 `-o addopts=""` 覆盖默认筛选，确保只运行 `llm_integration` 测试。

publish 相关测试分层：

- 默认 `pytest -q` 仅运行 mock/monkeypatch 的 publish 测试，不依赖真实 GitHub 写入。
- 如需真实 GitHub 写入 integration 测试，请单独在受控环境执行并显式设置真实 `GITHUB_TOKEN`。

## 简短 Roadmap

- 第 1 步：接入仓库读取与本地 clone 管理
- 第 2 步：接入 LLM 调用与贡献点分析
- 第 3 步：生成 patch 并执行本地验证
- 第 4 步：产出结构化 PR draft
