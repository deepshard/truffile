import argparse
import asyncio
import sys

from .guard import CLIGuard


_CLI_COMMANDS = {
    "agent",
    "chat",
    "connect",
    "create",
    "delete",
    "deploy",
    "disconnect",
    "glow",
    "help",
    "infer",
    "list",
    "load",
    "models",
    "obsidian",
    "resume",
    "run",
    "scan",
    "shell",
    "task",
    "validate",
}


def _normalize_cli_argv(argv: list[str]) -> list[str]:
    """Route a bare prompt into the interactive runtime.

    Exact command names retain command precedence, matching other agent CLIs.
    Use ``truffile -- PROMPT`` when a prompt starts with a dash.
    """
    if not argv or argv[0].startswith("-") or argv[0] in _CLI_COMMANDS:
        if argv and argv[0] == "--":
            return ["shell", "--new", "--", *argv[1:]]
        return argv
    return ["shell", "--new", "--", *argv]


def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


def main() -> int:
    guard = CLIGuard()
    with guard:
        return _main()
    return guard.code


_DEVICE_REQUIRING_COMMANDS = {
    None,  # default → chat
    "run",
    "resume",
    "shell",
    "agent",
    "chat",
    "infer",
    "deploy",
    "delete",
    "models",
    "task",
}


def _command_needs_device(args) -> bool:
    cmd = getattr(args, "command", None)
    if cmd == "deploy":
        return not bool(getattr(args, "dry_run", False))
    if cmd == "obsidian":
        return getattr(args, "obsidian_command", None) == "deploy" and not bool(getattr(args, "dry_run", False))
    if cmd in _DEVICE_REQUIRING_COMMANDS:
        return True
    if cmd == "list":
        return getattr(args, "what", "") == "apps"
    return False


def _normalize_device_name(raw: str) -> str:
    s = raw.strip()
    if not s:
        return s
    if s.lower().startswith("truffle-"):
        return s.lower()
    # accept bare number ("1234"), strip non-digits if present
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits:
        return f"truffle-{digits}"
    return s


def _run_onboarding(storage) -> int:
    """Interactively collect a device number and user id, then run cmd_connect.

    Returns 0 on success, non-zero on failure. On success, the storage object
    is updated in-place with the new device + last_used_device + client_user_id.
    """
    from .ui import C, MUSHROOM
    from .connect import cmd_connect
    from types import SimpleNamespace

    print()
    print(f"  {MUSHROOM} {C.BOLD}Welcome to truffile!{C.RESET}")
    print(f"  {C.DIM}Let's get you connected to your Truffle.{C.RESET}")
    print()

    try:
        raw_device = input(f"{C.CYAN}?{C.RESET} Truffle number (e.g. 1234 or truffle-1234): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return 130
    device_name = _normalize_device_name(raw_device)
    if not device_name:
        print(f"  {C.RED}A truffle number is required.{C.RESET}")
        return 1

    stored_uid = (storage.state.client_user_id or "").strip()
    default_hint = f" [{stored_uid}]" if stored_uid else ""
    try:
        raw_uid = input(f"{C.CYAN}?{C.RESET} User ID{default_hint}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return 130
    user_id = raw_uid or stored_uid
    if not user_id:
        print(f"  {C.RED}A user id is required.{C.RESET}")
        return 1

    print()
    print(f"  {C.DIM}Running:{C.RESET} {C.CYAN}truffile connect {device_name} --user-id {user_id}{C.RESET}")
    print()

    connect_args = SimpleNamespace(device=device_name, user_id=user_id)
    return run_async(cmd_connect(connect_args, storage))


def _main() -> int:
    from truffile import __version__

    parser = argparse.ArgumentParser(
        prog="truffile",
        description="Run persistent tasks on your Truffle. With no command, open an interactive session.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--resume", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # scan
    scan_p = sub.add_parser("scan", help="scan for truffle devices")
    scan_p.add_argument("--timeout", type=int, default=5)
    scan_p.add_argument("--json", action="store_true", help="emit discovered devices as JSON without prompting")
    scan_p.add_argument("--non-interactive", action="store_true", dest="non_interactive", help="list devices without prompting to connect")

    # connect
    conn_p = sub.add_parser("connect", help="connect to a truffle")
    conn_p.add_argument("device", help="device name (e.g. truffle-1234)")
    conn_p.add_argument("--user-id", type=str, default=None, dest="user_id", help="user id from recovery codes (skips interactive prompt)")

    # disconnect
    disc_p = sub.add_parser("disconnect", help="disconnect from device(s)")
    disc_p.add_argument("device", nargs="?", default="all")

    # create
    create_p = sub.add_parser("create", help="scaffold a new app")
    create_p.add_argument("name", nargs="?")
    create_p.add_argument("--path", type=str, default=None, help="base directory for the app")

    # validate
    val_p = sub.add_parser("validate", help="validate app directory")
    val_p.add_argument("path", nargs="?", default=".")

    # load bundled agent resources into a workspace
    load_p = sub.add_parser("load", help="copy bundled skills and example apps into the current workspace")
    load_p.add_argument("what", nargs="?", choices=["skills", "examples", "all"], default="all")
    load_p.add_argument("--path", type=str, default=".", help="workspace directory to copy resources into")
    load_p.add_argument("--force", action="store_true", help="replace existing copied resources")
    load_p.add_argument("--json", action="store_true", help="emit structured json")

    # deploy
    dep_p = sub.add_parser("deploy", help="deploy app to device")
    dep_p.add_argument("path", nargs="?", default=".")
    dep_p.add_argument("--shell", action="store_true", help=argparse.SUPPRESS)
    dep_p.add_argument("--interactive", "-i", action="store_true")
    dep_p.add_argument("--dry-run", action="store_true")
    dep_p.add_argument("--json", action="store_true", help="emit structured json")
    dep_p.add_argument("--non-interactive", action="store_true", dest="non_interactive", help="fail instead of prompting for input")
    dep_p.add_argument("--replace", action="store_true", help="replace an installed app with the same bundle id")
    dep_p.add_argument("--no-finalize", action="store_true", help=argparse.SUPPRESS)
    dep_p.add_argument("--vault", type=str, default=None, help=argparse.SUPPRESS)
    dep_p.add_argument("--pick-vault", action="store_true", dest="pick_vault", help=argparse.SUPPRESS)
    dep_p.add_argument("--advertise-host", type=str, default=None, dest="advertise_host", help=argparse.SUPPRESS)
    dep_p.add_argument("--bind-host", type=str, default=None, dest="bind_host", help=argparse.SUPPRESS)
    dep_p.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)
    dep_p.add_argument("--token", type=str, default=None, help=argparse.SUPPRESS)
    dep_p.add_argument("--obsidian-reconfigure", action="store_true", dest="obsidian_reconfigure", help=argparse.SUPPRESS)

    # list
    list_p = sub.add_parser("list", help="list apps or devices")
    list_p.add_argument("what", choices=["apps", "devices"])
    list_p.add_argument("--json", action="store_true", help="emit structured json")

    # delete
    del_p = sub.add_parser("delete", help="delete app from device")
    del_p.add_argument("selection", nargs="*", help="'all', app numbers, names, slugs, or uuids")

    # models
    sub.add_parser("models", help="list inference models")

    # persistent task workflows
    def add_agent_options(command_parser):
        command_parser.add_argument("--prompt-file", type=str, default=None, help="read prompt from file")
        command_parser.add_argument("--stdin", action="store_true", help="force read prompt from stdin")
        command_parser.add_argument("--app", action="append", default=None, help="attach app by exact name, unique slug, or uuid (repeatable)")
        command_parser.add_argument("--device", type=str, default=None, help="target a connected device explicitly")
        command_parser.add_argument("--json", action="store_true", help="emit one structured JSON result")
        command_parser.add_argument("--show-thinking", action="store_true", dest="show_thinking", help="include thinking summaries on stderr")
        command_parser.add_argument("--quiet", "-q", action="store_true", help="suppress progress on stderr")
        command_parser.add_argument("--timeout", type=float, default=None, help="maximum wall-clock seconds")

    run_p = sub.add_parser("run", help="run a task non-interactively")
    run_p.add_argument("prompt_words", nargs="*", metavar="PROMPT", help="prompt text")
    add_agent_options(run_p)
    run_context = run_p.add_mutually_exclusive_group()
    run_context.add_argument("--resume", metavar="TASK_ID", dest="resume_task_id", help="continue an exact task")
    run_context.add_argument("--last", action="store_true", help="continue the most recently updated task")
    run_p.add_argument("--ephemeral", action="store_true", help="delete the task after returning its result")
    run_p.set_defaults(agent_command="run")

    resume_p = sub.add_parser("resume", help="resume an interactive task")
    resume_p.add_argument("task_id", nargs="?", metavar="TASK_ID", help="task id to resume")
    resume_p.add_argument("prompt_words", nargs="*", metavar="PROMPT", help="optional first prompt")
    resume_p.add_argument("--last", action="store_true", help="resume the most recently updated task")
    resume_p.add_argument("--device", type=str, default=None, help="target a connected device explicitly")
    resume_p.set_defaults(agent_command="resume", interactive_resume=True)

    # Hidden compatibility alias for the bare interactive interface.
    shell_p = sub.add_parser("shell")
    shell_p.add_argument("task_id", nargs="?", metavar="TASK_ID", help="open a specific task")
    shell_p.add_argument("prompt_words", nargs="*", metavar="PROMPT", help=argparse.SUPPRESS)
    shell_p.add_argument("--resume", action="store_true", help="pick a task to resume")
    shell_p.add_argument("--new", action="store_true", help=argparse.SUPPRESS)
    shell_p.add_argument("--device", type=str, default=None, help="target a connected device explicitly")
    shell_p.set_defaults(agent_command="shell")

    # Deprecated namespace retained as a hidden compatibility route.
    agent_p = sub.add_parser("agent")
    agent_sub = agent_p.add_subparsers(dest="agent_command", metavar="COMMAND")

    agent_run = agent_sub.add_parser("run", help="start a new persistent agent task")
    agent_run.add_argument("prompt_words", nargs="*", help="prompt text")
    add_agent_options(agent_run)
    agent_run.add_argument("--ephemeral", action="store_true", help="delete the task after returning its result")

    agent_resume = agent_sub.add_parser("resume", help="continue an existing task")
    agent_resume.add_argument("task_id", nargs="?", help="task id to resume")
    agent_resume.add_argument("prompt_words", nargs="*", help="follow-up prompt text")
    agent_resume.add_argument("--last", action="store_true", help="resume the most recently updated task")
    add_agent_options(agent_resume)

    agent_continue = agent_sub.add_parser("continue", help="alias for agent resume --last")
    agent_continue.add_argument("prompt_words", nargs="*", help="follow-up prompt text")
    add_agent_options(agent_continue)

    agent_shell = agent_sub.add_parser("shell", help="open the interactive agent shell")
    agent_shell.add_argument("--resume", action="store_true", help="pick a task to resume")
    agent_shell.add_argument("--task-id", type=str, default=None, dest="task_id", help="open a specific task")
    agent_shell.add_argument("--device", type=str, default=None, help="target a connected device explicitly")

    # task resource management
    task_p = sub.add_parser("task", help="inspect and manage persistent tasks")
    task_sub = task_p.add_subparsers(dest="task_command")
    task_common = argparse.ArgumentParser(add_help=False)
    task_common.add_argument("--device", type=str, default=None, help="target a connected device explicitly")
    task_common.add_argument("--json", action="store_true", help="emit structured JSON")
    task_common.add_argument("--quiet", "-q", action="store_true", help="suppress progress on stderr")

    task_list = task_sub.add_parser("list", parents=[task_common], help="list tasks newest-first")
    task_list.add_argument("--limit", type=int, default=15, help="maximum tasks to return")

    task_show = task_sub.add_parser("show", parents=[task_common], help="show task state and latest result")
    task_show.add_argument("task_id")
    task_show.add_argument("--with-nodes", action="store_true", help="include the raw task graph in JSON")

    task_status = task_sub.add_parser("status", parents=[task_common], help="show concise task status")
    task_status.add_argument("task_id")

    task_logs = task_sub.add_parser("logs", parents=[task_common], help="show task history events")
    task_logs.add_argument("task_id")

    task_wait = task_sub.add_parser("wait", parents=[task_common], help="wait until a task settles or asks for input")
    task_wait.add_argument("task_id")
    task_wait.add_argument("--timeout", type=float, default=None, help="maximum seconds to wait")

    task_interrupt = task_sub.add_parser("interrupt", parents=[task_common], help="interrupt active task execution")
    task_interrupt.add_argument("task_id")

    task_rename = task_sub.add_parser("rename", parents=[task_common], help="rename a task")
    task_rename.add_argument("task_id")
    task_rename.add_argument("name")

    task_delete = task_sub.add_parser("delete", parents=[task_common], help="delete a task")
    task_delete.add_argument("task_id")
    task_delete.add_argument("--yes", "-y", action="store_true", help="confirm deletion noninteractively")

    # Deprecated legacy runtime retained as a hidden compatibility route.
    chat_p = sub.add_parser("chat")
    chat_p.add_argument("prompt_words", nargs="*", help="prompt text (joined). if omitted, drops into REPL")
    chat_p.add_argument("--resume", action="store_true", help="resume a previous task (interactive picker)")
    # one-shot prompt sources
    chat_p.add_argument("--prompt-file", type=str, default=None, help="read prompt from file")
    chat_p.add_argument("--stdin", action="store_true", help="force read prompt from stdin")
    # task targeting
    chat_p.add_argument("--task-id", type=str, default=None, dest="task_id", help="resume a specific task by id")
    chat_p.add_argument("--resume-last", action="store_true", dest="resume_last", help="resume the most recent task")
    # app attachment
    chat_p.add_argument("--app", action="append", default=None, help="attach app by name, slug, or uuid (repeatable)")
    # discovery
    chat_p.add_argument("--list-apps", action="store_true", dest="list_apps", help="list installed apps and exit")
    chat_p.add_argument("--list-tasks", nargs="?", const=15, type=int, default=None, dest="list_tasks", help="list recent tasks and exit (optional N, default 15)")
    # output
    chat_p.add_argument("--json", action="store_true", help="emit structured json result")
    chat_p.add_argument("--show-thinking", action="store_true", dest="show_thinking", help="include thinking summaries on stderr")
    chat_p.add_argument("--quiet", "-q", action="store_true", help="suppress decoration on stderr")
    chat_p.add_argument("--timeout", type=float, default=None, help="max seconds to wait for task to settle")
    chat_p.add_argument("--device", type=str, default=None, help="target a connected device explicitly")

    # infer (raw model inference)
    infer_p = sub.add_parser("infer", help="raw model inference")
    infer_p.add_argument("prompt_words", nargs="*", help="prompt text (joined). if omitted, drops into REPL")
    # conversation
    infer_p.add_argument("--system", type=str, default=None, help="system prompt")
    infer_p.add_argument("--prompt-file", type=str, default=None, help="read prompt from file")
    infer_p.add_argument("--stdin", action="store_true", help="force read prompt from stdin")
    # model
    infer_p.add_argument("--model", type=str, default=None, help="override default model")
    infer_p.add_argument("--list-models", action="store_true", help="list available models and exit")
    # sampling
    infer_p.add_argument("--temperature", type=float, default=None)
    infer_p.add_argument("--top-p", type=float, default=None, dest="top_p")
    infer_p.add_argument("--max-tokens", type=int, default=None, dest="max_tokens")
    infer_p.add_argument("--reasoning", choices=["on", "off"], default=None)
    infer_p.add_argument("--no-default-tools", action="store_true", help="disable web_search/web_fetch")
    infer_p.add_argument("--no-tools", action="store_true", help=argparse.SUPPRESS)  # deprecated alias
    infer_p.add_argument("--max-rounds", type=int, default=None, dest="max_rounds", help="max tool-use rounds")
    # output
    infer_p.add_argument("--json", action="store_true", help="emit structured json result")
    infer_p.add_argument("--show-reasoning", action="store_true", help="include reasoning in plain output")
    infer_p.add_argument("--stream", dest="force_stream", action="store_true", help="force streaming output")
    infer_p.add_argument("--no-stream", action="store_true", help="disable streaming output")
    infer_p.add_argument("--quiet", "-q", action="store_true", help="suppress decoration on stderr")
    # images
    infer_p.add_argument("--image", action="append", default=None, help="attach image (path or URL, repeatable)")
    # mcp
    infer_p.add_argument("--mcp", type=str, action="append", default=None, help="connect to MCP server (repeatable)")
    infer_p.add_argument("--list-tools", action="store_true", help="list available tools and exit")
    infer_p.add_argument("--call", type=str, default=None, help="call a tool by name and exit")
    infer_p.add_argument("--tool-args", type=str, default=None, dest="tool_args", help="JSON args for --call")
    # misc
    infer_p.add_argument("--timeout", type=float, default=None, help="per-request timeout in seconds")

    # help
    sub.add_parser("help", help="show help")

    # obsidian bridge + bundled app
    obs_p = sub.add_parser("obsidian", help="manage the local Obsidian bridge and app")
    obs_sub = obs_p.add_subparsers(dest="obsidian_command")

    obs_attach = obs_sub.add_parser("attach", help="save a local Obsidian vault bridge config")
    obs_attach.add_argument("--vault", required=False, help="path to a local Obsidian vault")
    obs_attach.add_argument("--pick-vault", action="store_true", dest="pick_vault", help="choose the vault from a native folder picker")
    obs_attach.add_argument("--port", type=int, default=27125, help="bridge port")
    obs_attach.add_argument("--bind-host", type=str, default="0.0.0.0", dest="bind_host", help="host interface for the bridge server")
    obs_attach.add_argument("--advertise-host", type=str, default=None, dest="advertise_host", help="host/IP the Truffle device should use")
    obs_attach.add_argument("--token", type=str, default=None, help="explicit bearer token for the bridge")

    obs_sub.add_parser("status", help="show saved Obsidian bridge configuration")
    obs_sub.add_parser("restart", help="restart the background Obsidian bridge")
    obs_logs = obs_sub.add_parser("logs", help="show recent Obsidian bridge logs")
    obs_logs.add_argument("--lines", type=int, default=40, help="number of log lines to print")
    obs_sub.add_parser("serve", help="run the local Obsidian bridge server")
    obs_test = obs_sub.add_parser("test", help="probe the Obsidian bridge locally and from the device")
    obs_test.add_argument("--local-only", action="store_true", dest="local_only", help="only test the bridge from this computer")

    obs_deploy = obs_sub.add_parser("deploy", help="deploy the bundled Obsidian app")
    obs_deploy.add_argument("--path", type=str, default=None, help="override the Obsidian app directory")
    obs_deploy.add_argument("--shell", action="store_true", help=argparse.SUPPRESS)
    obs_deploy.add_argument("--interactive", "-i", action="store_true")
    obs_deploy.add_argument("--dry-run", action="store_true")
    obs_deploy.add_argument("--no-finalize", action="store_true", help=argparse.SUPPRESS)

    # easter egg
    sub.add_parser("glow")

    args = parser.parse_args(_normalize_cli_argv(sys.argv[1:]))

    if args.command == "help":
        from .welcome import show_help_welcome
        show_help_welcome()
        return 0

    if args.command == "glow":
        from .art import render_glow_demo
        render_glow_demo(duration=999999.0)
        return 0

    from truffile.storage import StorageService, StoredDevice
    storage = StorageService()

    # in-container short-circuit: if we're running inside a Truffle app
    # container (APP_ID + APP_SESSION_TOKEN + GRPC_ADDRESS all set in env),
    # inject a synthetic device into in-memory storage pointing at the host
    # firmware. From here on, every device-requiring command resolves to it
    # without ever touching mDNS, persistence, or the onboarding prompt.
    from .in_container import probe_in_container_device
    _ic_info = probe_in_container_device()
    if _ic_info is not None:
        if not any(d.name == _ic_info.device_name for d in storage.state.devices):
            storage.state.devices.append(
                StoredDevice(name=_ic_info.device_name, token=_ic_info.session_token)
            )
        storage.state.last_used_device = _ic_info.device_name
        storage._in_container_info = _ic_info  # type: ignore[attr-defined]

    # first-run onboarding: if a device-requiring command was issued and there
    # is no connected device, walk the user through `truffile connect` first.
    if _command_needs_device(args) and not storage.state.last_used_device:
        rc = _run_onboarding(storage)
        if rc != 0:
            return rc

    if args.command is None:
        from .chat import cmd_chat
        from types import SimpleNamespace
        return run_async(cmd_chat(
            SimpleNamespace(resume=args.resume, prompt_words=[]),
            storage,
        ))

    if args.command == "scan":
        from .connect import cmd_scan
        return run_async(cmd_scan(args, storage))
    elif args.command == "connect":
        from .connect import cmd_connect
        return run_async(cmd_connect(args, storage))
    elif args.command == "disconnect":
        from .connect import cmd_disconnect
        return cmd_disconnect(args, storage)
    elif args.command == "create":
        from .create import cmd_create
        return cmd_create(args)
    elif args.command == "validate":
        from .validate import cmd_validate
        return cmd_validate(args)
    elif args.command == "load":
        from .load import cmd_load
        return cmd_load(args)
    elif args.command == "deploy":
        from .deploy import cmd_deploy
        return run_async(cmd_deploy(args, storage))
    elif args.command == "obsidian":
        from .obsidian import (
            cmd_obsidian_attach,
            cmd_obsidian_deploy,
            cmd_obsidian_logs,
            cmd_obsidian_restart,
            cmd_obsidian_serve,
            cmd_obsidian_status,
            cmd_obsidian_test,
        )

        if args.obsidian_command == "attach":
            return cmd_obsidian_attach(args, storage)
        elif args.obsidian_command == "status":
            return cmd_obsidian_status(args, storage)
        elif args.obsidian_command == "restart":
            return cmd_obsidian_restart(args, storage)
        elif args.obsidian_command == "logs":
            return cmd_obsidian_logs(args, storage)
        elif args.obsidian_command == "serve":
            return cmd_obsidian_serve(args, storage)
        elif args.obsidian_command == "test":
            return run_async(cmd_obsidian_test(args, storage))
        elif args.obsidian_command == "deploy":
            return run_async(cmd_obsidian_deploy(args, storage))
        parser.error("obsidian requires a subcommand")
    elif args.command == "list":
        from .apps import cmd_list
        return cmd_list(args, storage)
    elif args.command == "delete":
        from .apps import cmd_delete
        return run_async(cmd_delete(args, storage))
    elif args.command == "models":
        from .models import cmd_models
        return run_async(cmd_models(storage))
    elif args.command in {"run", "resume", "shell"}:
        from .agent import cmd_agent
        return run_async(cmd_agent(args, storage))
    elif args.command == "agent":
        if not args.agent_command:
            parser.error("agent requires run, resume, continue, or shell")
        if not getattr(args, "quiet", False):
            print(
                "warning: 'truffile agent' is deprecated; use 'truffile run' for scripts "
                "or bare 'truffile'/'truffile resume' interactively",
                file=sys.stderr,
            )
        from .agent import cmd_agent
        return run_async(cmd_agent(args, storage))
    elif args.command == "task":
        if not args.task_command:
            parser.error("task requires list, show, status, logs, wait, interrupt, rename, or delete")
        from .task import cmd_task
        return run_async(cmd_task(args, storage))
    elif args.command == "chat":
        if not getattr(args, "quiet", False):
            print(
                "warning: 'truffile chat' is deprecated; use 'truffile run' for scripts "
                "or bare 'truffile'/'truffile resume' interactively",
                file=sys.stderr,
            )
        from .chat import cmd_chat
        return run_async(cmd_chat(args, storage))
    elif args.command == "infer":
        from .infer import cmd_infer
        return run_async(cmd_infer(args, storage))

    from .welcome import show_help_welcome
    show_help_welcome()
    return 1
