from __future__ import annotations

from collections.abc import Callable

from snip.utils import run as _run
from snip.utils import run_streaming as _run_streaming

_IGNORE_HOSTS_OPTIONS = [
    "-o",
    "StrictHostKeyChecking=accept-new",
]


def make_ssh_args(
    user: str,
    host: str,
    port: int,
    ssh_options: list[str] | None = None,
) -> list[str]:
    args = ["ssh"]
    args.extend(_IGNORE_HOSTS_OPTIONS)
    if ssh_options:
        for opt in ssh_options:
            args.extend(["-o", opt])
    if port != 22:
        args.extend(["-p", str(port)])
    args.append(f"{user}@{host}")
    return args


def _maybe_sudo(user: str, cmd: list[str]) -> list[str]:
    if user == "root":
        return cmd
    return ["sudo", "--"] + cmd


async def realise(
    user: str,
    host: str,
    drv_path: str,
    port: int = 22,
    ssh_options: list[str] | None = None,
    *,
    on_line: Callable[[str], None] | None = None,
) -> str:
    ssh_base = make_ssh_args(user, host, port, ssh_options)
    realise_cmd = _maybe_sudo(user, ["nix-store", "--realise", drv_path])
    stdout, stderr, rc = await _run_streaming(
        ssh_base + realise_cmd,
        on_stderr=on_line,
        check=False,
    )
    if rc != 0:
        raise RuntimeError(f"nix-store --realise failed: {stderr.strip()}")
    return stdout.strip()


async def activate(
    user: str,
    host: str,
    store_path: str,
    port: int = 22,
    ssh_options: list[str] | None = None,
    *,
    on_line: Callable[[str], None] | None = None,
) -> list[str]:
    ssh_base = make_ssh_args(user, host, port, ssh_options)

    nix_env_cmd = _maybe_sudo(
        user,
        [
            "nix-env",
            "--profile",
            "/nix/var/nix/profiles/system",
            "--set",
            store_path,
        ],
    )
    _, stderr, rc = await _run(
        ssh_base + nix_env_cmd,
        check=False,
    )
    if rc != 0:
        raise RuntimeError(f"nix-env --set failed: {stderr.strip()}")

    switch_cmd = _maybe_sudo(
        user,
        [store_path + "/bin/switch-to-configuration", "switch"],
    )
    stdout, stderr, rc = await _run_streaming(
        ssh_base + switch_cmd,
        on_stdout=on_line,
        on_stderr=on_line,
        check=False,
    )
    if rc != 0:
        raise RuntimeError(f"switch-to-configuration failed: {stderr.strip()}")

    return [line for line in stdout.strip().split("\n") if line]
