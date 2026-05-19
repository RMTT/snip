from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys

from snip.commands import activate_cmd, build_cmd, deploy_cmd, list_cmd, push_cmd
from snip.models import SnipConfig
from snip.nix import eval_snip_config
from snip.ui import AnsiUI, Components, rewrite_display


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
    deploy_p.set_defaults(func=deploy_cmd)

    build_p = sub.add_parser("build", help="Build only")
    _add_common_args(build_p)
    build_p.add_argument(
        "--remote-build", action="store_true", help="force remote builds"
    )
    build_p.set_defaults(func=build_cmd)

    push_p = sub.add_parser("push", help="Build + copy")
    _add_common_args(push_p)
    push_p.add_argument(
        "--remote-build", action="store_true", help="force remote builds"
    )
    push_p.set_defaults(func=push_cmd)

    activate_p = sub.add_parser("activate", help="Activate already-pushed nodes")
    _add_common_args(activate_p)
    activate_p.set_defaults(func=activate_cmd)

    list_p = sub.add_parser("list", help="List all nodes")
    list_p.set_defaults(func=list_cmd)

    return parser


async def config_loader(args: argparse.Namespace) -> SnipConfig:
    async def _load() -> SnipConfig:
        remote_build = False
        if "remote_build" in args:
            remote_build = args.remote_build

        return await eval_snip_config(
            flake_ref=args.flake, remote_override=remote_build
        )

    task = asyncio.create_task(_load())
    frame_height = 0
    try:
        while not task.done():
            lines = Components.eval_loader(args.flake, False)

            rewrite_display(frame_height, lines)
            frame_height = len(lines)

            await asyncio.sleep(0.2)

        nodes_data = await task
        lines = Components.eval_loader(args.flake, True)
        rewrite_display(frame_height, lines)
        return nodes_data

    finally:
        sys.stdout.write(AnsiUI.SHOW)
        sys.stdout.flush()


async def _async_main(args: argparse.Namespace) -> int:
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(_run(args))

    def _on_sigint() -> None:
        main_task.cancel()

    loop.add_signal_handler(signal.SIGINT, _on_sigint)
    try:
        return await main_task
    except asyncio.CancelledError:
        while not main_task.done():
            await asyncio.sleep(0.5)
        print(f"\n{AnsiUI.AMBER}Cancelled.{AnsiUI.RESET}")
        return 130
    finally:
        loop.remove_signal_handler(signal.SIGINT)


async def _run(args: argparse.Namespace) -> int:
    try:
        args.flake = os.path.realpath(args.flake)
        config = await config_loader(args)
    except RuntimeError as e:
        msg = (
            f"{AnsiUI.BOLD}{AnsiUI.RED}"
            f"Failed to parse snip config:{AnsiUI.RESET}\n\n{e}"
        )
        print(msg)
        return 1

    success = await args.func(args, config)
    return 0 if success else 1


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    sys.exit(asyncio.run(_async_main(args)))
