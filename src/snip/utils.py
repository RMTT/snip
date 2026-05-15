from __future__ import annotations

import asyncio
from collections.abc import Callable


class BoundedList(list):
    def __init__(self, maxlen: int) -> None:
        super().__init__()
        self._maxlen = maxlen

    def append(self, item: str) -> None:
        super().append(item)
        if len(self) > self._maxlen:
            del self[0]


async def run(cmd: list[str], *, check: bool = True) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if check and proc.returncode != 0:
        raise RuntimeError(f"command: {' '.join(cmd)}\n{stderr.decode().strip()}")
    return stdout.decode(), stderr.decode(), proc.returncode or 0


async def run_streaming(
    cmd: list[str],
    *,
    on_stderr: Callable[[str], None] | None = None,
    on_stdout: Callable[[str], None] | None = None,
    check: bool = True,
) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _read(
        stream: asyncio.StreamReader | None,
        cb: Callable[[str], None] | None,
    ) -> str:
        if stream is None or cb is None:
            return (await stream.read()).decode() if stream else ""
        buf: list[str] = []
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode(errors="replace").rstrip("\n")
            buf.append(decoded)
            cb(decoded)
        return "\n".join(buf)

    stdout, stderr = await asyncio.gather(
        _read(proc.stdout, on_stdout),
        _read(proc.stderr, on_stderr),
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"command: {' '.join(cmd)}\n{stderr.strip()}")
    return stdout, stderr, proc.returncode or 0
