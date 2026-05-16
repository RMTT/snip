from __future__ import annotations

import asyncio
import sys

import pytest

from snip.cli import _async_main


class FakeArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    flake: str = "."
    command: str = "list"
    nodes: list[str] = []
    parallel: int | None = None
    dry_run: bool = False
    remote_build: bool = False


class _Exit(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


def _fake_exit(code: int = 0) -> None:
    raise _Exit(code)


@pytest.mark.asyncio
async def test_sigint_cancels_main_task(monkeypatch):
    async def _hang_forever(*args, **kwargs):
        await asyncio.sleep(9999)

    import snip.cli

    monkeypatch.setattr(snip.cli, "eval_snip_config", _hang_forever)
    monkeypatch.setattr(snip.cli, "eval_node_info", _hang_forever)
    monkeypatch.setattr(sys, "exit", _fake_exit)

    args = FakeArgs(command="list")

    task = asyncio.create_task(_async_main(args))

    await asyncio.sleep(0.1)
    task.cancel()

    with pytest.raises(_Exit) as exc_info:
        await task
    assert exc_info.value.code == 130
