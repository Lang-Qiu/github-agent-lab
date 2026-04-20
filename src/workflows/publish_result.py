"""Publish workflow helpers for sending local contribution results to GitHub."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .analyze_repo import parse_repo_url
from .publish_client import PublishClient, PublishClientError


class PublishResultError(ValueError):
    """User-facing input error for publish workflow."""


def _read_json_if_exists(file_path: Path) -> dict[str, object] | None:
    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


def _write_publish_result(output_dir: Path, payload: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_file = output_dir / "publish_result.json"
    result_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result_file


def _resolve_task_id(output_dir: Path, task_id: str | None) -> str | None:
    if task_id:
        return task_id

    run_task_result = _read_json_if_exists(output_dir / "run_task_result.json")
    if isinstance(run_task_result, dict):
        candidate = run_task_result.get("task_id")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    pr_draft_payload = _read_json_if_exists(output_dir / "pr_draft.json")
    if isinstance(pr_draft_payload, dict):
        candidate = pr_draft_payload.get("task_id")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def _resolve_workspace_dir(output_dir: Path, repo_url: str) -> str:
    _, repo = parse_repo_url(repo_url)
    summary_candidates = [
        output_dir / "summary.json",
        output_dir / f"{repo}_summary.json",
    ]

    for summary_file in summary_candidates:
        summary_payload = _read_json_if_exists(summary_file)
        if not isinstance(summary_payload, dict):
            continue

        workspace_dir = str(summary_payload.get("workspace_dir", "")).strip()
        if workspace_dir:
            return workspace_dir

    raise PublishResultError("repo summary not found. Run analyze first.")


def _build_publish_message(result: dict[str, object], result_file: Path) -> str:
    return (
        "Publish completed.\n"
        f"repo_url: {result['repo_url']}\n"
        f"task_id: {result['task_id']}\n"
        f"status: {result['status']}\n"
        f"branch: {result['branch_name']}\n"
        f"commit_sha: {result['commit_sha']}\n"
        f"pushed: {'true' if result['pushed'] else 'false'}\n"
        f"pr_created: {'true' if result['pr_created'] else 'false'}\n"
        f"pr_url: {result['pr_url']}\n"
        f"publish_result_file: {result_file.as_posix()}"
    )


def _run_git_command(workspace_dir: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", workspace_dir, *args]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def _ensure_git_ok(result: subprocess.CompletedProcess[str], action: str) -> None:
    if result.returncode == 0:
        return

    reason = result.stderr.strip() or result.stdout.strip() or f"git {action} failed"
    raise PublishResultError(f"git {action} failed: {reason}")


def _normalize_branch_name(task_id: str | None) -> str:
    task = (task_id or "task").strip().replace(" ", "-")
    return f"publish/{task}"


def _is_protected_branch(branch_name: str) -> bool:
    return branch_name in {"main", "master"}


def prepare_local_publish(
    workspace_dir: str,
    task_id: str | None,
    branch_name: str | None,
) -> dict[str, object]:
    status_result = _run_git_command(workspace_dir, ["status", "--porcelain"])
    _ensure_git_ok(status_result, "status")

    has_changes = bool(status_result.stdout.strip())
    if not has_changes:
        raise PublishResultError("No local changes to publish.")

    resolved_branch = (branch_name or "").strip() or _normalize_branch_name(task_id)
    if _is_protected_branch(resolved_branch):
        raise PublishResultError(
            f"Protected branch is not allowed for publish: {resolved_branch}"
        )

    current_branch_result = _run_git_command(workspace_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    _ensure_git_ok(current_branch_result, "rev-parse --abbrev-ref HEAD")

    current_branch = current_branch_result.stdout.strip()
    if current_branch != resolved_branch:
        branch_exists_result = _run_git_command(
            workspace_dir,
            ["show-ref", "--verify", "--quiet", f"refs/heads/{resolved_branch}"],
        )
        if branch_exists_result.returncode == 0:
            checkout_result = _run_git_command(workspace_dir, ["checkout", resolved_branch])
            _ensure_git_ok(checkout_result, f"checkout {resolved_branch}")
        else:
            checkout_result = _run_git_command(workspace_dir, ["checkout", "-b", resolved_branch])
            _ensure_git_ok(checkout_result, f"checkout -b {resolved_branch}")

    add_result = _run_git_command(workspace_dir, ["add", "-A"])
    _ensure_git_ok(add_result, "add -A")

    commit_message = f"chore: publish {task_id or 'task'} local contribution"
    commit_result = _run_git_command(workspace_dir, ["commit", "-m", commit_message])
    _ensure_git_ok(commit_result, "commit")

    sha_result = _run_git_command(workspace_dir, ["rev-parse", "HEAD"])
    _ensure_git_ok(sha_result, "rev-parse HEAD")

    return {
        "workspace_dir": workspace_dir,
        "branch_name": resolved_branch,
        "commit_message": commit_message,
        "commit_sha": sha_result.stdout.strip(),
        "has_changes": has_changes,
        "committed": True,
    }


def push_prepared_branch(
    workspace_dir: str,
    branch_name: str,
    commit_sha: str,
    publish_client: object,
    remote_name: str = "origin",
) -> dict[str, object]:
    remote_result = _run_git_command(workspace_dir, ["remote", "get-url", remote_name])
    if remote_result.returncode != 0:
        return {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pushed": False,
            "errors": [f"Git remote '{remote_name}' is not configured."],
        }

    try:
        push_result = publish_client.push_branch(
            workspace_dir=workspace_dir,
            branch_name=branch_name,
            remote_name=remote_name,
        )
        pushed = bool(push_result.get("pushed", False))
    except PublishClientError as exc:
        return {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pushed": False,
            "errors": [str(exc)],
        }
    except Exception as exc:  # pragma: no cover - defensive safety net
        return {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pushed": False,
            "errors": [str(exc)],
        }

    return {
        "branch_name": branch_name,
        "commit_sha": commit_sha,
        "pushed": pushed,
        "errors": [],
    }


def _load_draft_pr_content(output_dir: Path) -> tuple[str, str]:
    pr_json_file = output_dir / "pr_draft.json"
    pr_md_file = output_dir / "pr_draft.md"

    title = "chore: publish local contribution"

    if pr_json_file.exists():
        try:
            payload = json.loads(pr_json_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                title_candidate = str(payload.get("title", "")).strip()
                if title_candidate:
                    title = title_candidate
        except Exception:
            pass

    if pr_md_file.exists():
        body = pr_md_file.read_text(encoding="utf-8").strip()
        if body:
            return title, body

    if pr_json_file.exists():
        try:
            payload = json.loads(pr_json_file.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                summary = str(payload.get("summary", "")).strip()
                if summary:
                    body = f"## Summary\n\n{summary}\n"
                    return title, body
        except Exception:
            pass

    return title, "No local PR draft artifact found. Please review changes before merge."


def create_draft_pr_step(
    repo_url: str,
    branch_name: str,
    base_branch: str,
    publish_client: object,
    output_dir: Path,
) -> dict[str, object]:
    title, body = _load_draft_pr_content(output_dir)

    try:
        payload = publish_client.create_draft_pr(
            repo_url=repo_url,
            title=title,
            body=body,
            head=branch_name,
            base=base_branch,
        )
        pr_url = str(payload.get("url", "")).strip()
    except PublishClientError as exc:
        return {
            "pr_created": False,
            "pr_url": "",
            "errors": [str(exc)],
        }
    except Exception as exc:  # pragma: no cover - defensive safety net
        return {
            "pr_created": False,
            "pr_url": "",
            "errors": [str(exc)],
        }

    return {
        "pr_created": bool(pr_url),
        "pr_url": pr_url,
        "errors": [],
    }


def run_publish(
    repo_url: str,
    task_id: str | None = None,
    branch_name: str | None = None,
    draft_pr: bool = False,
    base_branch: str = "main",
) -> str:
    output_dir = Path("playground") / "outputs"
    resolved_task_id = _resolve_task_id(output_dir, task_id)

    base_result = {
        "repo_url": repo_url,
        "task_id": resolved_task_id,
        "branch_name": "",
        "commit_sha": "",
        "pushed": False,
        "pr_created": False,
        "pr_url": "",
        "status": "failed",
        "summary": "",
        "draft_pr": draft_pr,
        "errors": [],
    }

    try:
        workspace_dir = _resolve_workspace_dir(output_dir, repo_url)
        publish_client = PublishClient()
        if hasattr(publish_client, "verify_remote_repo"):
            publish_client.verify_remote_repo(repo_url)

        prepared = prepare_local_publish(
            workspace_dir=workspace_dir,
            task_id=resolved_task_id,
            branch_name=branch_name,
        )
    except PublishResultError as exc:
        result = dict(base_result)
        result["summary"] = f"Publish failed during local preparation: {exc}"
        result["errors"] = [str(exc)]
        result_file = _write_publish_result(output_dir, result)
        raise PublishResultError(str(exc)) from exc

    result = dict(base_result)
    result["branch_name"] = str(prepared.get("branch_name", ""))
    result["commit_sha"] = str(prepared.get("commit_sha", ""))

    push_result = push_prepared_branch(
        workspace_dir=workspace_dir,
        branch_name=result["branch_name"],
        commit_sha=result["commit_sha"],
        publish_client=publish_client,
    )

    result["pushed"] = bool(push_result.get("pushed", False))
    result["errors"].extend(list(push_result.get("errors", [])))

    if not result["pushed"]:
        result["status"] = "failed"
        result["summary"] = "Publish failed during push step."
        result_file = _write_publish_result(output_dir, result)
        return _build_publish_message(result, result_file)

    if draft_pr:
        pr_result = create_draft_pr_step(
            repo_url=repo_url,
            branch_name=result["branch_name"],
            base_branch=base_branch,
            publish_client=publish_client,
            output_dir=output_dir,
        )
        result["pr_created"] = bool(pr_result.get("pr_created", False))
        result["pr_url"] = str(pr_result.get("pr_url", ""))
        result["errors"].extend(list(pr_result.get("errors", [])))
    else:
        result["pr_created"] = False
        result["pr_url"] = ""

    if draft_pr and not result["pr_created"]:
        result["status"] = "partial"
        result["summary"] = "Branch pushed, but draft PR creation failed."
    else:
        result["status"] = "completed"
        if draft_pr:
            result["summary"] = "Publish completed with pushed branch and draft PR."
        else:
            result["summary"] = "Publish completed with pushed branch."

    result_file = _write_publish_result(output_dir, result)
    return _build_publish_message(result, result_file)
