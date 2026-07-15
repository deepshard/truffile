from __future__ import annotations

from typing import Any

from truffile.storage import StorageService

from .chat import _emit_oneshot_error, cmd_chat
from .exit_codes import USAGE


def _usage_error(args: Any, message: str) -> int:
    _emit_oneshot_error(
        message,
        json_out=bool(getattr(args, "json", False)),
        code="usage_error",
        device=getattr(args, "device", None),
        task_id=getattr(args, "task_id", None),
    )
    return USAGE


def _prepare_interactive(args: Any) -> None:
    defaults = {
        "prompt_words": [],
        "prompt_file": None,
        "stdin": False,
        "resume_last": False,
        "app": None,
        "list_apps": False,
        "list_tasks": None,
        "json": False,
        "show_thinking": False,
        "quiet": False,
        "timeout": None,
    }
    for name, value in defaults.items():
        if not hasattr(args, name):
            setattr(args, name, value)
    args.force_oneshot = False
    args.force_interactive = True
    args.ephemeral = False


async def cmd_agent(args: Any, storage: StorageService) -> int:
    command = args.agent_command

    if command == "run":
        args.task_id = getattr(args, "resume_task_id", None)
        args.resume_last = bool(getattr(args, "last", False))
        if (args.task_id or args.resume_last) and bool(getattr(args, "ephemeral", False)):
            return _usage_error(args, "--ephemeral cannot be combined with --resume or --last")
        args.resume = False
        args.force_oneshot = True
        return await cmd_chat(args, storage)

    if command == "resume":
        if getattr(args, "interactive_resume", False):
            if args.last:
                # argparse assigns the first positional token to task_id. For
                # the --last form that token is the optional first prompt.
                if args.task_id:
                    args.prompt_words = [args.task_id, *(args.prompt_words or [])]
                args.task_id = None
                args.resume_last = True
                args.resume = False
            else:
                args.resume_last = False
                args.resume = not bool(args.task_id)
            _prepare_interactive(args)
            return await cmd_chat(args, storage)

        if args.last:
            # argparse assigns the first positional token to task_id. For the
            # --last form that token is the first prompt word instead.
            if args.task_id:
                args.prompt_words = [args.task_id, *(args.prompt_words or [])]
            args.task_id = None
            args.resume_last = True
        else:
            if not args.task_id:
                return _usage_error(args, "resume requires TASK_ID or --last")
            args.resume_last = False
        args.resume = False
        args.force_oneshot = True
        args.ephemeral = False
        return await cmd_chat(args, storage)

    if command == "continue":
        args.task_id = None
        args.resume_last = True
        args.resume = False
        args.force_oneshot = True
        args.ephemeral = False
        return await cmd_chat(args, storage)

    if command == "shell":
        if getattr(args, "new", False):
            if args.task_id:
                args.prompt_words = [args.task_id, *(getattr(args, "prompt_words", None) or [])]
            args.task_id = None
            args.resume = False
        _prepare_interactive(args)
        return await cmd_chat(args, storage)

    return _usage_error(args, "expected run, resume, or shell")
