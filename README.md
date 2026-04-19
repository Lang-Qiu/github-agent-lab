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

- 不接入真实 GitHub Token
- 不实现完整业务流程
- 不做前端、部署、多用户系统

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

运行 llm_integration 测试前必须提供真实 LLM 环境变量：

```bash
set LLM_API_KEY=your_real_key
set LLM_BASE_URL=your_real_base_url
set LLM_MODEL=your_real_model
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
pytest -q -m llm_integration -o addopts="" tests/test_llm_integration.py -k run_task
```

说明：
- 上述命令会执行 `run-task` 并开启 `--use-llm-discover`、`--use-llm-plan`、`--use-llm-patch`、`--use-llm-apply`、`--use-llm-validate`、`--use-llm-pr-draft`。
- 建议在网络稳定、配额充足时运行，以减少因外部服务导致的波动。

说明：
- 默认 `pytest -q` 通过 `llm_integration` marker 隔离真实 LLM 测试。
- 集成测试命令通过 `-o addopts=""` 覆盖默认筛选，确保只运行 `llm_integration` 测试。

## 简短 Roadmap

- 第 1 步：接入仓库读取与本地 clone 管理
- 第 2 步：接入 LLM 调用与贡献点分析
- 第 3 步：生成 patch 并执行本地验证
- 第 4 步：产出结构化 PR draft
