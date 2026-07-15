#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROMPTS = APP_DIR / "prompts" / "whoop_cli_prompts.txt"
DEFAULT_OUT = APP_DIR / "artifacts" / "whoop-cli"


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    error: str | None = None


@dataclass
class PromptRun:
    result: CommandResult
    payload: dict[str, Any] | None
    validation_error: str | None
    warnings: list[str]
    settle_attempts: list[dict[str, Any]]


def _slug(value: str) -> str:
    return value.lower().replace(" ", "-")


def _resolve_app_ref(ref: str, apps: list[dict[str, Any]]) -> dict[str, Any] | None:
    ref_s = ref.strip()
    ref_l = ref_s.lower()
    for app in apps:
        if app.get("uuid") == ref_s:
            return app
    for app in apps:
        if str(app.get("name", "")).lower() == ref_l:
            return app
    for app in apps:
        if _slug(str(app.get("name", ""))) == ref_l:
            return app
    for app in apps:
        if ref_l in str(app.get("name", "")).lower():
            return app
    return None


def _parse_prompt_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    prompts: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            block = "\n".join(current).strip()
            if block:
                prompts.append(block)
            current = []
        else:
            current.append(line)
    block = "\n".join(current).strip()
    if block:
        prompts.append(block)
    return prompts


def _run(command: list[str], *, timeout: float | None) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            error=f"command not found: {command[0]} ({exc})",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            error=f"command timed out after {timeout} seconds",
        )


def _load_json(stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "stdout JSON was not an object"
    return payload, None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _content_preview(content: Any, *, limit: int = 180) -> str:
    text = " ".join(str(content or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _make_run_dir(base: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = base / stamp
    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate
    for index in range(2, 1000):
        candidate = base / f"{stamp}-{index}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise RuntimeError(f"could not create unique run directory under {base}")


def _list_apps(truffile: str, *, timeout: float | None) -> tuple[list[dict[str, Any]] | None, str | None]:
    result = _run([truffile, "list", "apps", "--json"], timeout=timeout)
    if result.returncode != 0:
        detail = result.error or result.stderr.strip() or result.stdout.strip() or "unknown error"
        return None, f"`truffile list apps --json` failed: {detail}"
    payload, error = _load_json(result.stdout)
    if error:
        return None, f"`truffile list apps --json` returned invalid JSON: {error}"
    apps = payload.get("apps") if payload else None
    if not isinstance(apps, list):
        return None, "`truffile list apps --json` did not include an apps list"
    return [app for app in apps if isinstance(app, dict)], None


def _peek_task(
    *,
    truffile: str,
    task_id: str,
    timeout: float | None,
) -> tuple[CommandResult, dict[str, Any] | None, str | None]:
    command = [truffile, "task", "show", task_id, "--quiet", "--json"]
    result = _run(command, timeout=timeout)
    if result.returncode != 0:
        detail = result.error or result.stderr.strip() or result.stdout.strip() or "unknown error"
        return result, None, f"settle command failed: {detail}"
    payload, error = _load_json(result.stdout)
    if error:
        return result, None, f"settle command returned invalid JSON: {error}"
    return result, payload, None


def _record_settle_attempt(
    *,
    attempt: int,
    result: CommandResult,
    payload: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "command": result.command,
        "exit_code": result.returncode,
        "error": error,
        "task_id": payload.get("task_id") if payload else None,
        "pending_user_response": payload.get("pending_user_response") if payload else None,
        "content_preview": _content_preview(payload.get("content") if payload else ""),
        "stdout": result.stdout if error else None,
        "stderr": result.stderr if error else None,
        "command_error": result.error,
    }


def _validate_payload(
    payload: dict[str, Any],
    *,
    fail_on_pending: bool,
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    content = str(payload.get("content") or "").strip()
    if not content:
        return "response content was empty", warnings
    if payload.get("pending_user_response") is True:
        message = "response is waiting for a follow-up user message"
        if fail_on_pending:
            return message, warnings
        warnings.append(message)
    return None, warnings


def _run_prompt(
    *,
    truffile: str,
    app_ref: str,
    prompt: str,
    timeout: float | None,
    settle_checks: int,
    settle_delay: float,
    fail_on_pending: bool,
) -> PromptRun:
    prompt_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
            handle.write(prompt)
            handle.write("\n")
            prompt_path = Path(handle.name)
        command = [
            truffile,
            "run",
            "--quiet",
            "--json",
            "--app",
            app_ref,
            "--prompt-file",
            str(prompt_path),
        ]
        result = _run(command, timeout=timeout)
    finally:
        if prompt_path is not None:
            try:
                prompt_path.unlink()
            except OSError:
                pass

    if result.returncode != 0:
        detail = result.error or result.stderr.strip() or result.stdout.strip() or "unknown error"
        return PromptRun(result, None, f"command failed: {detail}", [], [])
    payload, error = _load_json(result.stdout)
    if error:
        return PromptRun(result, None, f"invalid JSON response: {error}", [], [])

    settle_attempts: list[dict[str, Any]] = []
    warnings: list[str] = []
    task_id = str(payload.get("task_id") or "")
    for attempt in range(1, max(0, settle_checks) + 1):
        content = str(payload.get("content") or "").strip()
        pending = payload.get("pending_user_response") is True
        if content and not pending:
            break
        if not task_id:
            break
        if settle_delay > 0:
            time.sleep(settle_delay)
        settle_result, settle_payload, settle_error = _peek_task(
            truffile=truffile,
            task_id=task_id,
            timeout=timeout,
        )
        settle_attempts.append(
            _record_settle_attempt(
                attempt=attempt,
                result=settle_result,
                payload=settle_payload,
                error=settle_error,
            )
        )
        if settle_error:
            warnings.append(f"settle check {attempt} failed: {settle_error}")
            break
        if settle_payload is not None:
            payload = settle_payload

    validation_error, validation_warnings = _validate_payload(payload, fail_on_pending=fail_on_pending)
    warnings.extend(validation_warnings)
    return PromptRun(result, payload, validation_error, warnings, settle_attempts)


def _failure_artifact(
    *,
    prompt_index: int,
    prompt: str,
    result: CommandResult,
    validation_error: str,
    parsed_payload: dict[str, Any] | None,
    warnings: list[str],
    settle_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "error",
        "prompt_index": prompt_index,
        "prompt": prompt,
        "validation_error": validation_error,
        "warnings": warnings,
        "parsed_payload": parsed_payload,
        "settle_attempts": settle_attempts,
        "command": result.command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command_error": result.error,
    }


def _summary_row(
    *,
    prompt_index: int,
    prompt: str,
    result: CommandResult,
    payload: dict[str, Any] | None,
    validation_error: str | None,
    warnings: list[str],
    settle_attempts: list[dict[str, Any]],
    artifact: Path,
) -> dict[str, Any]:
    return {
        "prompt_index": prompt_index,
        "exit_code": result.returncode,
        "ok": validation_error is None,
        "task_id": payload.get("task_id") if payload else None,
        "attached_apps": payload.get("attached_apps") if payload else None,
        "tool_calls": payload.get("tool_calls") if payload else None,
        "pending_user_response": payload.get("pending_user_response") if payload else None,
        "content_preview": _content_preview(payload.get("content") if payload else ""),
        "prompt_preview": _content_preview(prompt),
        "artifact": str(artifact),
        "error": validation_error,
        "warnings": warnings,
        "settle_attempts": len(settle_attempts),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run prompt-file tests against a deployed WHOOP Truffle app.",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS,
        help=f"prompt file to run; blocks are separated by lines containing only --- (default: {DEFAULT_PROMPTS})",
    )
    parser.add_argument("--app", default="whoop", help="Truffle app name, slug, or uuid to attach")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"artifact root (default: {DEFAULT_OUT})")
    parser.add_argument("--truffile", default="truffile", help="truffile executable path (default: truffile)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="per truffile command timeout in seconds (default: no subprocess timeout)",
    )
    parser.add_argument(
        "--settle-checks",
        type=int,
        default=1,
        help="number of task-status polls after a pending or empty response before starting the next prompt (default: 1)",
    )
    parser.add_argument(
        "--settle-delay",
        type=float,
        default=0.5,
        help="seconds to wait before each settle poll (default: 0.5)",
    )
    parser.add_argument(
        "--fail-on-pending",
        action="store_true",
        help="treat pending_user_response=true as a failure even when response content is present",
    )
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first failed prompt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt_path = args.prompts.expanduser()
    if not prompt_path.is_file():
        print(f"prompt file not found: {prompt_path}", file=sys.stderr)
        return 2

    try:
        prompts = _parse_prompt_file(prompt_path)
    except OSError as exc:
        print(f"could not read prompt file: {exc}", file=sys.stderr)
        return 2
    if not prompts:
        print(f"prompt file did not contain any prompts: {prompt_path}", file=sys.stderr)
        return 2

    apps, app_error = _list_apps(args.truffile, timeout=args.timeout)
    if app_error:
        print(app_error, file=sys.stderr)
        return 1
    matched_app = _resolve_app_ref(args.app, apps or [])
    if matched_app is None:
        app_names = ", ".join(str(app.get("name") or app.get("uuid") or "<unnamed>") for app in apps or [])
        print(f"could not find app matching {args.app!r}. Installed apps: {app_names}", file=sys.stderr)
        return 1

    run_dir = _make_run_dir(args.out.expanduser())
    summary_path = run_dir / "summary.jsonl"
    app_name = str(matched_app.get("name") or args.app)
    app_uuid = str(matched_app.get("uuid") or "")
    print(f"WHOOP app: {app_name}" + (f" ({app_uuid})" if app_uuid else ""))
    print(f"Prompts: {len(prompts)}")
    print(f"Artifacts: {run_dir}")

    failures = 0
    with summary_path.open("w", encoding="utf-8") as summary:
        for index, prompt in enumerate(prompts, start=1):
            print(f"[{index}/{len(prompts)}] running: {_content_preview(prompt, limit=90)}")
            prompt_run = _run_prompt(
                truffile=args.truffile,
                app_ref=args.app,
                prompt=prompt,
                timeout=args.timeout,
                settle_checks=args.settle_checks,
                settle_delay=args.settle_delay,
                fail_on_pending=args.fail_on_pending,
            )
            result = prompt_run.result
            payload = prompt_run.payload
            validation_error = prompt_run.validation_error
            artifact_path = run_dir / f"{index:03d}.json"
            if validation_error is None and payload is not None:
                _write_json(artifact_path, payload)
            else:
                failures += 1
                _write_json(
                    artifact_path,
                    _failure_artifact(
                        prompt_index=index,
                        prompt=prompt,
                        result=result,
                        validation_error=validation_error or "unknown validation error",
                        parsed_payload=payload,
                        warnings=prompt_run.warnings,
                        settle_attempts=prompt_run.settle_attempts,
                    ),
                )

            row = _summary_row(
                prompt_index=index,
                prompt=prompt,
                result=result,
                payload=payload,
                validation_error=validation_error,
                warnings=prompt_run.warnings,
                settle_attempts=prompt_run.settle_attempts,
                artifact=artifact_path,
            )
            summary.write(json.dumps(row, ensure_ascii=False) + "\n")
            summary.flush()
            if validation_error is None:
                print(f"[{index}/{len(prompts)}] ok: {_content_preview(payload.get('content'), limit=90)}")
                for warning in prompt_run.warnings:
                    print(f"[{index}/{len(prompts)}] warning: {warning}", file=sys.stderr)
            else:
                print(f"[{index}/{len(prompts)}] failed: {validation_error}", file=sys.stderr)
                if args.fail_fast:
                    break

    print(f"Summary: {summary_path}")
    if failures:
        print(f"Failed prompts: {failures}", file=sys.stderr)
        return 1
    print("All prompts completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
