from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from snip.models import SnipConfig
from snip.utils import run as _run
from snip.utils import run_streaming as _run_streaming

_APPLY_STRIP_CONFIG = r"""
x: {
  defaults = x.defaults or { };
  nodes = builtins.mapAttrs (
    n: v:
    let
      hasConfig = v ? config && v.config != null && v.config != "";
      targetAttr = if hasConfig then "snip.nodes.${n}.config" else "";
    in
    (builtins.removeAttrs v [ "config" ]) // { config = targetAttr; }
  ) x.nodes;
}
"""

_GET_NODE_INFO = r"""
let
  flake = builtins.getFlake (builtins.toString <flakePath>);
  nodes = flake.snip.nodes or {};
  
  extract = name: node:
    let
      cfg = if (node ? config && node.config != "") then node.config 
            else flake.nixosConfigurations.${name};
    in {
      system = cfg.config.nixpkgs.hostPlatform.system;
      path = builtins.toString cfg.config.system.build.toplevel;
    };
in
  builtins.mapAttrs extract nodes
"""


async def eval_node_info(flake: str) -> dict[str, dict[str, Any]]:
    expr = _GET_NODE_INFO.replace("<flakePath>", flake)
    stdout, _, _ = await _run(["nix", "eval", "--impure", "--json", "--expr", expr])
    return json.loads(stdout)


async def eval_snip_config(
    flake_ref: str = ".",
) -> SnipConfig:
    cmd = ["nix", "eval", "--json", f"{flake_ref}#snip", "--apply", _APPLY_STRIP_CONFIG]
    stdout, _, _ = await _run(cmd)
    data = json.loads(stdout)
    return SnipConfig.from_json(flake_ref, data)


async def build_toplevel(
    config_path: str,
    *,
    remote: bool = False,
    ssh_target: str | None = None,
    on_line: Callable[[str], None] | None = None,
) -> str:
    attr = f"{config_path}.config.system.build.toplevel"
    cmd = ["nix", "build", attr, "--no-link", "--print-out-paths"]
    if remote and ssh_target:
        cmd.extend(["--store", f"ssh-ng://{ssh_target}"])
    stdout, _, _ = await _run_streaming(cmd, on_stderr=on_line)
    return stdout.strip()


async def copy_closure(
    store_path: str,
    ssh_target: str,
    *,
    on_line: Callable[[str], None] | None = None,
) -> None:
    await _run_streaming(
        ["nix", "copy", "--to", f"ssh-ng://{ssh_target}", store_path],
        on_stderr=on_line,
    )


async def eval_toplevel_outpath(config_path: str) -> str:
    attr = f"{config_path}.config.system.build.toplevel.outPath"
    stdout, _, _ = await _run(["nix", "eval", "--raw", attr])
    return stdout.strip()
