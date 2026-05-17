from __future__ import annotations

import json
from collections.abc import Callable

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


async def eval_node_info(flake: str) -> dict[str, dict[str, str]]:
    expr = _GET_NODE_INFO.replace("<flakePath>", flake)
    stdout, _, _ = await _run(["nix", "eval", "--impure", "--json", "--expr", expr])
    return json.loads(stdout)


async def eval_snip_config(
    flake_ref: str = ".", remote_override: bool = False
) -> SnipConfig:
    cmd = ["nix", "eval", "--json", f"{flake_ref}#snip", "--apply", _APPLY_STRIP_CONFIG]
    stdout, _, _ = await _run(cmd)
    data: dict = json.loads(stdout)

    # apply cmd overrides
    for node in data.get("nodes", {}).values():
        if remote_override:
            node["remoteBuild"] = remote_override

    return SnipConfig.from_json(flake_ref, data)


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


async def eval_drvpath(config_path: str) -> str:
    attr = f"{config_path}.config.system.build.toplevel.drvPath"
    stdout, _, _ = await _run(["nix", "eval", "--raw", attr])
    return stdout.strip()


async def copy_closure(
    store_path: str,
    ssh_target: str,
    *,
    on_line: Callable[[str], None] | None = None,
) -> None:
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
    )


async def eval_toplevel_outpath(config_path: str) -> str:
    attr = f"{config_path}.config.system.build.toplevel.outPath"
    stdout, _, _ = await _run(["nix", "eval", "--raw", attr])
    return stdout.strip()
