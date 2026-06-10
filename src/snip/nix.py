from __future__ import annotations

import json
import os
from collections.abc import Callable

from snip.models import SnipConfig
from snip.utils import run as _run
from snip.utils import run_streaming as _run_streaming

# ----------------------------------------------------------------------------
# Nix Expressions
# ----------------------------------------------------------------------------

_EVAL_SNIP_CONFIG = r"""
let
  flake = builtins.getFlake (builtins.toString <flakePath>);
  snipConfig = flake.snip or {};

  defaults = snipConfig.defaults or {};
  nodes = snipConfig.nodes or {};

  processNode = name: v:
    let
      hasConfig = v ? config && v.config != null && v.config != "";
      targetAttr = if hasConfig then "snip.nodes.${name}.config" else "";
      cfg = if hasConfig then v.config else flake.nixosConfigurations.${name};
    in
    (builtins.removeAttrs v [ "config" ]) // {
      config = targetAttr;
    };
in {
  defaults = defaults;
  nodes = builtins.mapAttrs processNode nodes;
}
"""


# ----------------------------------------------------------------------------
# Configuration Evaluation
# ----------------------------------------------------------------------------


async def eval_snip_config(
    flake_ref: str = ".", remote_override: bool = False
) -> SnipConfig:
    expr = _EVAL_SNIP_CONFIG.replace("<flakePath>", flake_ref)
    cmd = ["nix", "eval", "--impure", "--json", "--expr", expr]
    stdout, _, _ = await _run(cmd)
    data: dict = json.loads(stdout)

    # apply cmd overrides
    for node in data.get("nodes", {}).values():
        if remote_override:
            node["remoteBuild"] = remote_override

    return SnipConfig.from_json(flake_ref, data)


# ----------------------------------------------------------------------------
# Nix Store & Build Operations
# ----------------------------------------------------------------------------


async def eval_toplevel_attr(config_path: str, attr_name: str) -> str:
    attr = f"{config_path}.config.system.build.toplevel.{attr_name}"
    stdout, _, _ = await _run(["nix", "eval", "--raw", attr])
    return stdout.strip()


async def eval_system(config_path: str) -> str:
    attr = f"{config_path}.config.nixpkgs.hostPlatform.system"
    stdout, _, _ = await _run(["nix", "eval", "--raw", attr])
    return stdout.strip()


async def realise(
    drv_path: str,
    *,
    on_line: Callable[[str], None] | None = None,
) -> str:
    cmd = ["nix-store", "--realise", drv_path]
    stdout, stderr, rc = await _run_streaming(cmd, on_stderr=on_line, check=False)
    if rc != 0:
        raise RuntimeError(f"nix-store --realise failed: {stderr.strip()}")
    return stdout.strip()


async def copy_closure(
    store_path: str,
    ssh_target: str,
    *,
    port: int = 22,
    ssh_options: list[str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    env = os.environ.copy()
    ssh_opts_str = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
    if port != 22:
        ssh_opts_str += f"-p {port} "
    if ssh_options:
        for opt in ssh_options:
            ssh_opts_str += f"-o {opt} "

    if ssh_opts_str:
        existing_ssh_opts = env.get("NIX_SSHOPTS", "")
        env["NIX_SSHOPTS"] = f"{existing_ssh_opts} {ssh_opts_str}".strip()

    await _run_streaming(
        [
            "nix",
            "copy",
            "--no-check-sigs",
            "--to",
            f"ssh-ng://{ssh_target}?compress=true",
            store_path,
        ],
        on_stderr=on_line,
        env=env,
    )
