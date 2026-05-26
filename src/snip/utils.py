from __future__ import annotations

import asyncio
from collections.abc import Callable


async def run(
    cmd: list[str], *, check: bool = True, env: dict[str, str] | None = None
) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        proc.terminate()
        await proc.wait()
        raise

    if check and proc.returncode != 0:
        raise RuntimeError(f"command: {' '.join(cmd)}\n{stderr.decode().strip()}")
    return stdout.decode(), stderr.decode(), proc.returncode or 0


async def _read_stream(
    stream: asyncio.StreamReader | None,
    cb: Callable[[str], None] | None,
) -> str:
    if stream is None or cb is None:
        return (await stream.read()).decode(errors="replace") if stream else ""
    buf: list[str] = []
    while True:
        line = await stream.readline()
        if not line:
            break
        decoded = line.decode(errors="replace").rstrip("\n")
        buf.append(decoded)
        cb(decoded)
    return "\n".join(buf)


async def run_streaming(
    cmd: list[str],
    *,
    on_stderr: Callable[[str], None] | None = None,
    on_stdout: Callable[[str], None] | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.gather(
            _read_stream(proc.stdout, on_stdout),
            _read_stream(proc.stderr, on_stderr),
        )
    except asyncio.CancelledError:
        proc.terminate()
        await proc.wait()
        raise

    if check and proc.returncode != 0:
        raise RuntimeError(f"command: {' '.join(cmd)}\n{stderr.strip()}")
    return stdout, stderr, proc.returncode or 0
