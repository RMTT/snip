from __future__ import annotations

import argparse
import asyncio
import fnmatch
import os
import re
import signal
import sys

from snip.deploy import run_activate, run_build, run_deploy, run_push
from snip.models import SnipConfig
from snip.nix import eval_node_info, eval_snip_config
from snip.ui import AnsiUI, Components, render_node_table, rewrite_display


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("nodes", nargs="*", help="node names or glob patterns")
    p.add_argument("--parallel", type=int, default=None, help="max concurrent deploys")
    p.add_argument("--dry-run", action="store_true", help="show what would be deployed")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snip", description="NixOS deployment tool")
    parser.add_argument("--flake", default=".", help="flake path (default: .)")

    sub = parser.add_subparsers(dest="command")

    deploy_p = sub.add_parser("deploy", help="Build, copy, and activate nodes")
    _add_common_args(deploy_p)
    deploy_p.add_argument(
        "--remote-build", action="store_true", help="force remote builds"
    )

    build_p = sub.add_parser("build", help="Build only")
    _add_common_args(build_p)
    build_p.add_argument(
        "--remote-build", action="store_true", help="force remote builds"
    )

    push_p = sub.add_parser("push", help="Build + copy")
    _add_common_args(push_p)
    push_p.add_argument(
        "--remote-build", action="store_true", help="force remote builds"
    )

    activate_p = sub.add_parser("activate", help="Activate already-pushed nodes")
    _add_common_args(activate_p)

    sub.add_parser("list", help="List all nodes")

    return parser


def _parse_patterns(raw: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(fnmatch.translate(p)) for p in raw if p]


def _filter_nodes(config_nodes: dict, args: argparse.Namespace) -> list[str]:
    names = list(config_nodes.keys())
    if hasattr(args, "nodes") and args.nodes:
        patterns = _parse_patterns(args.nodes)
        names = [n for n in names if any(p.match(n) for p in patterns)]
    return names


async def config_loader(args: argparse.Namespace) -> SnipConfig:
    async def _load() -> SnipConfig:
        remote_build = False
        if "remote_build" in args:
            remote_build = args.remote_build

        config_task = eval_snip_config(
            flake_ref=args.flake, remote_override=remote_build
        )
        info_task = eval_node_info(flake=args.flake)

        config, extra_node_info = await asyncio.gather(config_task, info_task)

        for node in extra_node_info:
            if node in config.nodes:
                config.nodes[node].update_nodeinfo(extra_node_info[node])

        return config

    tasks = asyncio.create_task(_load())
    frame_height = 0
    try:
        while not tasks.done():
            lines = Components.eval_loader(args.flake, False)

            rewrite_display(frame_height, lines)
            frame_height = len(lines)

            await asyncio.sleep(0.2)

        nodes_data = await tasks
        lines = Components.eval_loader(args.flake, True)
        rewrite_display(frame_height, lines)
        return nodes_data

    finally:
        sys.stdout.write(AnsiUI.SHOW)
        sys.stdout.flush()


async def _async_main(args: argparse.Namespace) -> None:
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(_run(args))

    def _on_sigint() -> None:
        main_task.cancel()

    loop.add_signal_handler(signal.SIGINT, _on_sigint)
    try:
        await main_task
    except asyncio.CancelledError:
        while not main_task.done():
            await asyncio.sleep(0.5)
        print(f"\n{AnsiUI.AMBER}Cancelled.{AnsiUI.RESET}")
        sys.exit(130)
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def _run(args: argparse.Namespace) -> None:
    try:
        args.flake = os.path.realpath(args.flake)
        config = await config_loader(args)
    except RuntimeError as e:
        msg = (
            f"{AnsiUI.BOLD}{AnsiUI.RED}"
            f"Failed to parse snip config:{AnsiUI.RESET}\n\n{e}"
        )
        print(msg)
        return

    if args.command == "list":
        print("\n".join(render_node_table(config.nodes, args.flake)))
        return

    node_names = _filter_nodes(config.nodes, args)

    if not node_names:
        print(f"{AnsiUI.AMBER}No matching nodes found{AnsiUI.RESET}")
        return

    if args.dry_run:
        print(
            f"{AnsiUI.BOLD}Dry run:{AnsiUI.RESET} would deploy: {', '.join(node_names)}"
        )
        return

    if args.command == "deploy":
        await run_deploy(
            config,
            node_names,
            parallel=args.parallel,
        )
    elif args.command == "build":
        await run_build(
            config,
            node_names,
            parallel=args.parallel,
        )
    elif args.command == "push":
        await run_push(
            config,
            node_names,
            parallel=args.parallel,
        )
    elif args.command == "activate":
        await run_activate(
            config,
            node_names,
            parallel=args.parallel,
        )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    asyncio.run(_async_main(args))
