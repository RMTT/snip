from __future__ import annotations

import argparse
import fnmatch
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from snip.deploy import run_activate, run_build, run_deploy, run_push
from snip.ui import AnsiUI, render_node_table

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
    print("\n".join(render_node_table(config.nodes, args.flake)))


async def deploy_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_deploy)


async def build_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_build)


async def push_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_push)


async def activate_cmd(args: argparse.Namespace, config: SnipConfig) -> None:
    await _handle_command(args, config, run_activate)
