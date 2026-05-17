from __future__ import annotations

import argparse
import asyncio
import fnmatch
import re
import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from snip.deploy import run_activate, run_build, run_deploy, run_push
from snip.nix import eval_system
from snip.ui import AnsiUI, ListProgress, render_dynamic_node_table, rewrite_display

if TYPE_CHECKING:
    from snip.models import SnipConfig


def _parse_patterns(raw: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(fnmatch.translate(p)) for p in raw if p]


def _filter_nodes(config_nodes: dict, args: argparse.Namespace) -> list[str]:
    names = list(config_nodes.keys())
    if hasattr(args, "nodes") and args.nodes:
        patterns = _parse_patterns(args.nodes)
        names = [n for n in names if any(p.match(n) for p in patterns)]
    return names


async def _handle_command(
    args: argparse.Namespace,
    config: SnipConfig,
    action_fn: Callable[..., Awaitable[None]],
) -> None:
    node_names = _filter_nodes(config.nodes, args)

    if not node_names:
        print(f"{AnsiUI.AMBER}No matching nodes found{AnsiUI.RESET}")
        return

    if getattr(args, "dry_run", False):
        print(
            f"{AnsiUI.BOLD}Dry run:{AnsiUI.RESET} would deploy: {', '.join(node_names)}"
        )
        return

    await action_fn(
        config,
        node_names,
        args.parallel,
    )


async def list_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    progress_map = {name: ListProgress() for name in config.nodes}
    tasks = []

    async def _fetch_system(name: str, config_path: str) -> None:
        try:
            sys_val = await eval_system(config_path)
            progress_map[name].system = sys_val
        except Exception:
            progress_map[name].system = "unknown"
        finally:
            progress_map[name].done = True

    for name, node in config.nodes.items():
        tasks.append(asyncio.create_task(_fetch_system(name, node.config)))

    sys.stdout.write(AnsiUI.HIDE)
    frame_height = 0
    try:
        while not all(t.done() for t in tasks):
            frame = render_dynamic_node_table(config.nodes, args.flake, progress_map)
            frame_height = rewrite_display(frame_height, frame)
            await asyncio.sleep(0.2)

        # Final render
        frame = render_dynamic_node_table(config.nodes, args.flake, progress_map)
        rewrite_display(frame_height, frame)
    finally:
        sys.stdout.write(AnsiUI.SHOW)
        sys.stdout.flush()


async def deploy_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_deploy)


async def build_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_build)


async def push_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_push)


async def activate_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_activate)
