from __future__ import annotations

import itertools
import math
import shutil
import sys
import textwrap
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snip.models import NodeConfig


class AnsiUI:
    # colors
    CYAN: str = "\033[38;5;117m"
    LIME: str = "\033[38;5;150m"
    AMBER: str = "\033[38;5;216m"
    SLATE: str = "\033[38;5;244m"
    VOID: str = "\033[38;5;236m"
    RED: str = "\033[1;31m"

    # style
    BOLD: str = "\033[1m"
    ITALIC: str = "\033[3m"

    # control
    RESET: str = "\033[0m"
    HIDE: str = "\033[?25l"
    SHOW: str = "\033[?25h"
    CLEAR: str = "\033[K"

    @staticmethod
    def up(n: int) -> str:
        return f"\033[{n}A" if n > 0 else ""

    @staticmethod
    def max_column() -> int:
        return shutil.get_terminal_size().columns


class Components:
    _SPINNER = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])

    @staticmethod
    def header(title: str, subtitle: str = "") -> list[str]:
        return [
            f"{AnsiUI.BOLD}{title}{AnsiUI.RESET} {subtitle}",
            f"{AnsiUI.VOID}{'━' * (len(title) + len(subtitle) + 4)}{AnsiUI.RESET}",
        ]

    @staticmethod
    def dynamic_node(
        node: NodeProgress,
        start_time: float = 0.0,
        pulse_width: int = 30,
    ) -> list[str]:
        name = node.name
        phase = node.phase.value
        status = _status_from_phase(node.phase)

        icon: str = {
            "run": f"{AnsiUI.CYAN}●",
            "ok": f"{AnsiUI.LIME}✔",
            "err": f"{AnsiUI.AMBER}✘",
        }.get(status, f"{AnsiUI.SLATE}○")

        if status == "ok":
            pulse_bar: str = f"{AnsiUI.LIME}{'━' * pulse_width}{AnsiUI.RESET}"
        elif status == "err":
            pulse_bar: str = f"{AnsiUI.AMBER}{'━' * pulse_width}{AnsiUI.RESET}"
        else:
            p_width: int = 6
            elapsed: float = time.time() - start_time
            pos: float = (math.sin(elapsed * 4) + 1) / 2
            offset: int = int(pos * (pulse_width - p_width))

            pulse_bar = (
                f"{AnsiUI.VOID}{'·' * offset}{AnsiUI.RESET}"
                f"{AnsiUI.CYAN}{'━' * p_width}{AnsiUI.RESET}"
                f"{AnsiUI.VOID}{'·' * (pulse_width - offset - p_width)}{AnsiUI.RESET}"
            )

        sp = f"{AnsiUI.SLATE}│{AnsiUI.RESET}"
        node_line = (
            f"{icon}{AnsiUI.RESET} "
            f"{AnsiUI.BOLD}{name:<14}{AnsiUI.RESET}"
            f"{sp} {phase:<8} {pulse_bar}"
        )
        lines = [node_line]

        # construct subtitlelines
        subtitle_color = f"{AnsiUI.CYAN}"
        if node.phase == DeployPhase.FAILED:
            subtitle_color = AnsiUI.RED
        max_log_width = max(10, AnsiUI.max_column() - 3)
        if len(node.logs) > 0:
            latest_log = node.logs[-1]
            if len(latest_log) > max_log_width:
                latest_log = latest_log[:max_log_width]
                latest_log = latest_log[:-3] + "..."
            lines.append(f" {subtitle_color}↳ {latest_log}{AnsiUI.RESET}")
        lines.append(f" {subtitle_color}↳ {node.current_status}{AnsiUI.RESET}")

        return lines

    @staticmethod
    def static_node(name: str) -> list[str]:
        dot: str = f"{AnsiUI.LIME}●{AnsiUI.RESET}"
        return [
            f"{dot}  {AnsiUI.BOLD}{name:<14}{AnsiUI.RESET}",
        ]

    @staticmethod
    def eval_loader(path: str, done: bool) -> list[str]:
        lines = []
        char = next(Components._SPINNER)
        if done:
            char = "✅"

        lines.append(
            f"{AnsiUI.CYAN}{char}{AnsiUI.RESET} {AnsiUI.BOLD}"
            f"Evaluating flake:{AnsiUI.RESET} {AnsiUI.ITALIC}{path}{AnsiUI.RESET}"
        )
        lines.append(f"{AnsiUI.VOID}{'━' * 40}{AnsiUI.RESET}")

        return lines

    @staticmethod
    def summary(nodes: list[NodeProgress], action: str) -> list[str]:
        lines = []

        failed_nodes = [n for n in nodes if n.phase == DeployPhase.FAILED]
        total_count = len(nodes)

        lines.append("")

        node_str = "nodes" if total_count > 1 else "node"
        if not failed_nodes:
            msg = f"All {total_count} {node_str} updated successfully."
            lines.append(
                f"{AnsiUI.LIME}🎉 {action.upper()} SUCCESS{AnsiUI.RESET}"
                f" {AnsiUI.SLATE}» {msg}{AnsiUI.RESET}"
            )
            lines.append(f" {AnsiUI.VOID}{'━' * 50}{AnsiUI.RESET}")
            return lines

        msg = f"{len(failed_nodes)} out of {total_count} {node_str} reported errors"
        lines.append(
            f"{AnsiUI.RED}✖ {action.upper()} FAILED{AnsiUI.RESET}"
            f" {AnsiUI.SLATE}» {msg}{AnsiUI.RESET}"
        )
        lines.append(f"{AnsiUI.VOID}{'━' * 40}{AnsiUI.RESET}")

        for node in failed_nodes:
            lines.extend(Components.node_error_report(node))
            lines.append("")

        return lines

    @staticmethod
    def node_error_report(node: NodeProgress) -> list[str]:
        lines = []
        sp = f"{AnsiUI.RED}│{AnsiUI.RESET}"

        lines.append(
            f"{AnsiUI.RED}✘{AnsiUI.RESET} {AnsiUI.BOLD}{node.name}{AnsiUI.RESET}"
        )

        error_msg = str(node.error)

        max_w = max(10, AnsiUI.max_column() - 3)

        is_first_line = True
        for raw_line in str(error_msg).split("\n"):
            if is_first_line:
                lines.append(f" {sp} {AnsiUI.RED}Error:{AnsiUI.RESET}")
                is_first_line = False

            wrapped_parts = textwrap.wrap(raw_line, width=max_w, break_long_words=True)
            if not wrapped_parts:
                wrapped_parts = [""]

            for part in wrapped_parts:
                lines.append(f" {sp} {part}")

        lines.append(f" {sp}")

        # print logs
        logs = getattr(node, "logs", [])
        if not logs:
            lines.append(
                f" {AnsiUI.RED}└─{AnsiUI.RESET}"
                f" {AnsiUI.SLATE}(No logs captured){AnsiUI.RESET}"
            )
            return lines

        tail_logs = logs[-5:]
        hint = "Last 5 lines of log" if len(logs) > 5 else "Full log output"

        lines.append(f" {sp} {AnsiUI.AMBER}{hint}:{AnsiUI.RESET}")

        log_max_w = max(10, AnsiUI.max_column() - 3)
        for log in tail_logs:
            safe_log = log if len(log) <= log_max_w else log[: log_max_w - 3] + "..."
            lines.append(f" {sp} {safe_log}")

        if node.log_path:
            lines.append(
                f" {AnsiUI.RED}└─{AnsiUI.RESET}"
                f" {AnsiUI.SLATE}📝Full log saved to {node.log_path}{AnsiUI.RESET}"
            )
        else:
            lines.append(
                f" {AnsiUI.RED}└─{AnsiUI.RESET}"
                f" {AnsiUI.SLATE}📝Full log not saved{AnsiUI.RESET}"
            )

        return lines


class DeployPhase(Enum):
    QUEUED = "queued"
    BUILDING = "building"
    PUSHING = "pushing"
    ACTIVATING = "activating"
    DONE = "done"
    FAILED = "failed"


@dataclass
class NodeProgress:
    name: str
    phase: DeployPhase = DeployPhase.QUEUED
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=10))
    current_status: str = "preparing"
    error: Exception | None = None
    store_path: str | None = None
    log_path: str | None = None
    start_time: float = field(default_factory=time.time)


@dataclass
class ListProgress:
    done: bool = False
    system: str = "unknown"


def _status_from_phase(phase: DeployPhase) -> str:
    if phase == DeployPhase.DONE:
        return "ok"
    if phase == DeployPhase.FAILED:
        return "err"
    return "run"


def _truncate_store_path(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 4 and len(parts[3]) > 3:
        hash_name = parts[3]
        dash_idx = hash_name.find("-")
        if dash_idx > 0:
            return f"store...{hash_name[:dash_idx][-3:]}"
    return path


def rewrite_display(prev_height: int, frame: list[str]) -> int:
    if prev_height > 0:
        sys.stdout.write(AnsiUI.up(prev_height))

    new_height = 0
    for line in frame:
        sys.stdout.write(f"{AnsiUI.CLEAR}{line}\n")
        new_height += line.count("\n") + 1

    sys.stdout.flush()
    return new_height


def render_deploy(nodes: list[NodeProgress], action: str) -> list[str]:
    lines: list[str] = []

    lines.extend(
        Components.header("snip deploy", f"» {AnsiUI.AMBER}{action}{AnsiUI.RESET}")
    )

    for node in nodes:
        node_lines = Components.dynamic_node(
            node,
            start_time=node.start_time,
        )
        lines.extend(node_lines)

    all_done = all(n.phase in (DeployPhase.DONE, DeployPhase.FAILED) for n in nodes)
    if all_done:
        lines.extend(Components.summary(nodes, action))

    return lines


def render_dynamic_node_table(
    nodes: Mapping[str, NodeConfig],
    flake: str,
    progress: Mapping[str, ListProgress],
) -> list[str]:
    lines = []

    lines.append(
        f"{AnsiUI.BOLD}snip list{AnsiUI.RESET} {AnsiUI.SLATE}"
        f"» {len(nodes)} nodes found in {flake}{AnsiUI.RESET}"
    )
    rule_len = int(AnsiUI.max_column() / 2)
    lines.append(f"{AnsiUI.VOID}{'━' * rule_len}{AnsiUI.RESET}")

    for name, node in nodes.items():
        node_progress = progress.get(name, ListProgress())
        icon = (
            f"{AnsiUI.CYAN}●{AnsiUI.RESET}"
            if node_progress.done
            else f"{AnsiUI.CYAN}{next(Components._SPINNER)}{AnsiUI.RESET}"
        )
        system_str = node_progress.system if node_progress.done else "evaluating..."
        metadata = (
            f"{icon} {AnsiUI.BOLD}{name}{AnsiUI.RESET}"
            f" {AnsiUI.SLATE}{system_str}{AnsiUI.RESET}"
            f" {AnsiUI.AMBER}·{AnsiUI.RESET} {node.host}"
            f" {AnsiUI.AMBER}·{AnsiUI.RESET} {AnsiUI.SLATE}{node.user}{AnsiUI.RESET}"
        )
        lines.append(metadata)
        lines.append("")

    return lines


def render_node_table(nodes: Mapping[str, NodeConfig], flake: str) -> list[str]:
    lines = []

    lines.append(
        f"{AnsiUI.BOLD}snip list{AnsiUI.RESET} {AnsiUI.SLATE}"
        f"» {len(nodes)} nodes found in {flake}{AnsiUI.RESET}"
    )
    rule_len = int(AnsiUI.max_column() / 2)
    lines.append(f"{AnsiUI.VOID}{'━' * rule_len}{AnsiUI.RESET}")

    for name in nodes:
        node = nodes[name]
        icon = f"{AnsiUI.CYAN}●{AnsiUI.RESET}"
        metadata = (
            f"{icon} {AnsiUI.BOLD}{name}{AnsiUI.RESET}"
            f" {AnsiUI.SLATE}{node.system}{AnsiUI.RESET}"
            f" {AnsiUI.AMBER}·{AnsiUI.RESET} {node.host}"
            f" {AnsiUI.AMBER}·{AnsiUI.RESET} {AnsiUI.SLATE}{node.user}{AnsiUI.RESET}"
        )
        lines.append(metadata)
        lines.append("")

    return lines
