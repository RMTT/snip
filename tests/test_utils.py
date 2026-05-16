from __future__ import annotations

import asyncio

import pytest

from snip.utils import run, run_streaming


@pytest.mark.asyncio
async def test_run_terminates_subprocess_on_cancel():
    async def _cancel_after(proc_task: asyncio.Task, delay: float) -> None:
        await asyncio.sleep(delay)
        proc_task.cancel()

    task = asyncio.create_task(run(["sleep", "60"]))
    asyncio.create_task(_cancel_after(task, 0.1))

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_run_streaming_terminates_subprocess_on_cancel():
    collected: list[str] = []

    async def _cancel_after(proc_task: asyncio.Task, delay: float) -> None:
        await asyncio.sleep(delay)
        proc_task.cancel()

    task = asyncio.create_task(
        run_streaming(
            ["sleep", "60"],
            on_stderr=lambda line: collected.append(line),
        )
    )
    asyncio.create_task(_cancel_after(task, 0.1))

    with pytest.raises(asyncio.CancelledError):
        await task
