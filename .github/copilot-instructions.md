# Repository-wide Copilot Instructions

## Project identity

This repository is a local experimental project for exploring LLM-driven GitHub contribution automation.

It is **not** a production system, not a deployed service, and not a polished demo project.
The current goal is to build a small, runnable, locally iterated codebase that can gradually grow from:
- repository analysis
- issue/task suggestion
- patch generation
- local validation
- PR draft generation

Prefer simple, incremental progress over big frameworks or speculative architecture.

---

## Current stage

The repository is currently in an early bootstrapping phase.

When making changes, optimize for:
- minimal runnable functionality
- clear local iteration
- low complexity
- easy refactoring later

Avoid introducing architecture intended for future scale unless it is directly needed by the current task.

---

## Core development principles

1. Keep changes **small, focused, and reversible**.
2. Prefer **the simplest implementation that works**.
3. Do not make unrelated edits.
4. Do not refactor broadly unless the task explicitly requires it.
5. Preserve a clear upgrade path, but do not over-engineer.
6. Favor readable code over clever code.
7. Prefer local file-based outputs over infrastructure-heavy solutions.

---

## Scope boundaries

Unless explicitly requested, do **not** introduce:
- frontend applications
- web dashboards
- databases
- message queues
- cloud deployment code
- Docker orchestration
- CI/CD pipelines
- authentication systems
- multi-user features
- background worker systems
- complex plugin systems
- abstract base class hierarchies for future use

This project should remain a lightweight local CLI-first experiment.

---

## Language and tooling expectations

Default stack:
- Python 3.11+
- Typer for CLI
- pytest for testing
- pyproject.toml for project metadata and dependencies

When adding dependencies:
- keep the dependency list small
- prefer standard library when reasonable
- avoid adding libraries without a concrete need
- explain why a new dependency is necessary

---

## Repository structure expectations

Respect the current repository layout and extend it conservatively.

Main areas:
- `src/` for application code
- `src/agents/` for agent role placeholders or implementations
- `src/workflows/` for orchestration flows
- `prompts/` for reusable prompt text files
- `playground/` for local experimental outputs, logs, and repo workspaces
- `tests/` for automated tests

Do not reorganize the whole repository unless explicitly asked.

---

## CLI expectations

This repository is CLI-first.

When implementing CLI behavior:
- keep commands easy to discover via `--help`
- provide clear command output
- prefer explicit, readable options and arguments
- keep placeholder commands honest about what is implemented and what is not
- do not fake real integrations

If a command is not fully implemented, return a clear placeholder or structured stub result rather than pretending to complete the task.

---

## GitHub integration rules

GitHub-related features should be introduced gradually.

Current preference:
- start with parsing repository URLs
- prepare local analysis context
- generate structured outputs
- add real GitHub API integration only when required

Unless explicitly requested:
- do not require real GitHub tokens
- do not assume network access is available
- do not automatically push to remote repositories
- do not automatically create branches, PRs, comments, or issues on GitHub

Favor local simulation or placeholder implementations first.

---

## LLM integration rules

LLM integration should also be introduced gradually.

Unless explicitly requested:
- do not call real model APIs
- do not hardcode real API keys or secrets
- do not assume a specific model provider
- do not build a complicated provider abstraction too early

At this stage, placeholders, stubs, or clearly separated client wrappers are preferred.

---

## Secrets and environment handling

Never hardcode:
- API keys
- tokens
- passwords
- local machine-specific secrets

Use:
- environment variables
- `.env.example` for templates
- safe defaults when possible

Do not print secrets in logs, examples, or CLI output.

---

## Testing expectations

Testing should stay lightweight but real.

Preferred approach:
- add or update tests for behavior that is actually being implemented
- start with small smoke tests and focused unit tests
- avoid giant test scaffolds for unimplemented systems
- do not add brittle snapshot tests unless they are clearly useful

When making a behavior change:
- update or add the smallest meaningful test
- keep test names descriptive
- keep tests fast

If following TDD for a task:
- write a small failing test first
- implement the minimum needed to pass
- stop once the requested behavior is complete

---

## File and code style guidance

When generating or editing code:
- keep modules small
- keep functions focused
- prefer explicit names
- avoid deeply nested logic where possible
- add docstrings only when they clarify intent
- avoid noisy comments that restate the code
- use type hints when they improve clarity
- avoid placeholder abstractions that are not used yet

Do not generate large empty frameworks or template-heavy boilerplate.

---

## Output and artifact conventions

When a workflow produces results, prefer saving them as local artifacts under `playground/outputs/` or another clearly named local directory.

Artifacts should be:
- easy to inspect
- easy to delete
- clearly named
- structured when possible (for example JSON or Markdown)

Avoid hidden magic behavior.

---

## Prompts and agent modules

The repository may contain role-based agent modules such as:
- scout
- planner
- coder
- validator
- pr_writer

Treat these as lightweight, evolvable components.

Do not assume the project already needs a sophisticated multi-agent runtime.
Simple sequential orchestration is preferred unless the task clearly requires more.

Prompt files in `prompts/` should remain:
- short
- specific
- easy to revise
- aligned with the current codebase state

---

## Git and commit guidance

Keep changes cohesive and commit-friendly.

When preparing changes:
- keep one logical task per change set
- avoid mixing cleanup with feature work
- do not modify unrelated files just to “improve” them
- prefer conventional, descriptive commit messages

Do not auto-push unless explicitly requested.
Do not commit directly to `main` or `master` unless explicitly requested.

---

## Documentation expectations

Documentation should match the actual implementation level.

Prefer:
- short, accurate README updates
- honest notes about current capabilities
- simple roadmap bullets

Do not document features as complete if they are only placeholders.

---

## Communication style in generated output

When summarizing work:
- be concrete
- mention what was actually implemented
- mention what is still placeholder
- list changed files when useful
- keep suggestions incremental

Avoid exaggerated claims like:
- “fully autonomous”
- “production-ready”
- “complete end-to-end platform”
unless that is truly the case

---

## Decision rule for future changes

When unsure between a simple solution and a more abstract solution, choose the simple one.

A good change in this repository usually has these properties:
- small
- local
- testable
- understandable
- easy to revise later

If a task would significantly expand project scope, implement the smallest viable slice first.