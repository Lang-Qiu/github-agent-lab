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
- 不调用真实 LLM API
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
pytest
```

## 简短 Roadmap

- 第 1 步：接入仓库读取与本地 clone 管理
- 第 2 步：接入 LLM 调用与贡献点分析
- 第 3 步：生成 patch 并执行本地验证
- 第 4 步：产出结构化 PR draft
