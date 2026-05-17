from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Protocol

from snip import nix, ssh
from snip.models import NodeConfig, SnipConfig
from snip.ui import (
    AnsiUI,
    DeployPhase,
    NodeProgress,
    render_deploy,
    rewrite_display,
)


class DeployStep(Protocol):
    async def run(self, node: NodeConfig, progress: NodeProgress) -> None: ...


class BuildStep:
    async def run(self, node: NodeConfig, progress: NodeProgress) -> None:
        try:
            progress.phase = DeployPhase.BUILDING

            progress.current_status = f"evaluating derivation for {node.name}"
            drv_path = await nix.eval_toplevel_attr(node.config, "drvPath")

            if node.remote_build:
                ssh_target = f"{node.user}@{node.host}"
                progress.current_status = f"copying derivation to {node.host}"
                await nix.copy_closure(
                    drv_path,
                    ssh_target,
                    on_line=lambda line: progress.logs.append(line),
                )

                progress.current_status = f"building {node.name} on {node.host}"
                progress.store_path = await ssh.realise(
                    node.user,
                    node.host,
                    drv_path,
                    port=node.port,
                    ssh_options=node.ssh_options,
                    on_line=lambda line: progress.logs.append(line),
                )
            else:
                progress.current_status = f"building {node.name}"
                progress.store_path = await nix.realise(
                    drv_path,
                    on_line=lambda line: progress.logs.append(line),
                )

            progress.phase = DeployPhase.DONE
        except RuntimeError as e:
            progress.phase = DeployPhase.FAILED
            progress.error = e
            raise


class PushStep:
    async def run(self, node: NodeConfig, progress: NodeProgress) -> None:
        if node.remote_build:
            progress.phase = DeployPhase.DONE
            return

        if progress.store_path is None:
            progress.phase = DeployPhase.FAILED
            progress.error = RuntimeError("no store path to push")
            raise progress.error

        try:
            progress.phase = DeployPhase.PUSHING
            progress.current_status = f"pushing {node.config} to {node.host}"
            await nix.copy_closure(
                progress.store_path,
                f"{node.user}@{node.host}",
                on_line=lambda line: progress.logs.append(line),
            )
            progress.phase = DeployPhase.DONE
        except RuntimeError as e:
            progress.phase = DeployPhase.FAILED
            progress.error = e
            raise


class ActivateStep:
    async def run(self, node: NodeConfig, progress: NodeProgress) -> None:
        if progress.store_path is None:
            progress.phase = DeployPhase.FAILED
            progress.error = RuntimeError("no store path to activate")
            raise progress.error

        try:
            progress.phase = DeployPhase.ACTIVATING
            progress.current_status = f"activating {node.config} on {node.host}"

            await ssh.activate(
                node.user,
                node.host,
                progress.store_path,
                port=node.port,
                ssh_options=node.ssh_options,
                on_line=lambda line: progress.logs.append(line),
            )
            progress.phase = DeployPhase.DONE
        except RuntimeError as e:
            progress.phase = DeployPhase.FAILED
            progress.error = e
            raise


class EvalStorePathStep:
    async def run(self, node: NodeConfig, progress: NodeProgress) -> None:
        try:
            progress.phase = DeployPhase.BUILDING
            progress.current_status = f"resolving store path for {node.name}"
            store_path = await nix.eval_toplevel_attr(node.config, "outPath")
            progress.store_path = store_path
            progress.phase = DeployPhase.DONE
        except Exception as e:
            progress.phase = DeployPhase.FAILED
            progress.error = e
            raise


def _save_failed_logs(progress_map: dict[str, NodeProgress]) -> None:
    for name, progress in progress_map.items():
        if progress.phase != DeployPhase.FAILED:
            continue
        if not progress.logs:
            continue
        temp_dir = tempfile.gettempdir()
        timestamp = int(time.time())
        pid = os.getpid()
        log_path_str = f"{temp_dir}/snip-{name}-{pid}-{timestamp}.log"
        log_path = Path(log_path_str)
        log_path.write_text("\n".join(progress.logs) + "\n")
        progress.log_path = log_path_str


async def run_steps(
    config: SnipConfig,
    node_names: list[str],
    steps: list[DeployStep],
    action_label: str,
    parallel: int | None = None,
) -> None:
    progress_map: dict[str, NodeProgress] = {
        name: NodeProgress(name=name) for name in node_names
    }

    semaphore = asyncio.Semaphore(parallel or len(node_names))

    async def _run(name: str) -> None:
        node = config.nodes[name]
        progress = progress_map[name]
        async with semaphore:
            try:
                for step in steps:
                    await step.run(node, progress)
                progress.phase = DeployPhase.DONE
            except Exception as e:
                if progress.error is None:
                    progress.phase = DeployPhase.FAILED
                    progress.error = e

    tasks = [asyncio.create_task(_run(name)) for name in node_names]

    sys.stdout.write(AnsiUI.HIDE)
    frame_height = 0
    try:
        while not all(t.done() for t in tasks):
            nodes_list = list(progress_map.values())
            frame = render_deploy(nodes_list, action_label)
            frame_height = rewrite_display(frame_height, frame)
            await asyncio.sleep(0.1)

        for t in tasks:
            try:
                await t
            except RuntimeError:
                pass

        _save_failed_logs(progress_map)

        nodes_list = list(progress_map.values())
        frame = render_deploy(nodes_list, action_label)
        rewrite_display(frame_height, frame)
    finally:
        sys.stdout.write(AnsiUI.SHOW)
        sys.stdout.flush()


async def run_build(
    config: SnipConfig,
    node_names: list[str],
    parallel: int | None = None,
) -> None:
    await run_steps(
        config,
        node_names,
        [BuildStep()],
        action_label="building",
        parallel=parallel,
    )


async def run_push(
    config: SnipConfig,
    node_names: list[str],
    parallel: int | None = None,
) -> None:
    await run_steps(
        config,
        node_names,
        [BuildStep(), PushStep()],
        action_label="pushing",
        parallel=parallel,
    )


async def run_activate(
    config: SnipConfig,
    node_names: list[str],
    parallel: int | None = None,
) -> None:
    await run_steps(
        config,
        node_names,
        [EvalStorePathStep(), ActivateStep()],
        action_label="activating",
        parallel=parallel,
    )


async def run_deploy(
    config: SnipConfig,
    node_names: list[str],
    parallel: int | None = None,
) -> None:
    await run_steps(
        config,
        node_names,
        [BuildStep(), PushStep(), ActivateStep()],
        action_label="deploying",
        parallel=parallel,
    )
