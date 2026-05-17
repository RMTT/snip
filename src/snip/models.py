from __future__ import annotations

import getpass
from dataclasses import dataclass, field


@dataclass
class NodeDefaults:
    user: str = "root"
    port: int = 22
    remote_build: bool = False
    ssh_options: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> NodeDefaults:
        return cls(
            user=data.get("user", getpass.getuser()),
            port=data.get("port", 22),
            remote_build=data.get("remoteBuild", False),
            ssh_options=data.get("sshOptions", []),
        )


@dataclass
class Defaults:
    nodes: NodeDefaults = field(default_factory=NodeDefaults)

    @classmethod
    def from_json(cls, data: dict) -> Defaults:
        return cls(nodes=NodeDefaults.from_json(data.get("nodes", {})))


@dataclass
class NodeConfig:
    name: str
    host: str
    user: str
    port: int
    remote_build: bool
    ssh_options: list[str]
    config: str
    system: str = "unknown"
    out_path: str | None = None

    @classmethod
    def from_json(
        cls, flake_ref: str, name: str, data: dict, defaults: NodeDefaults
    ) -> NodeConfig:
        config = data.get("config") or f"nixosConfigurations.{name}"
        config = f"{flake_ref}#{config}"

        return cls(
            name=name,
            host=data.get("host", name),
            user=data.get("user", defaults.user),
            port=data.get("port", defaults.port),
            remote_build=data.get("remoteBuild", defaults.remote_build),
            ssh_options=data.get("sshOptions", defaults.ssh_options),
            config=config,
            system=data.get("system", "unknown"),
            out_path=data.get("out_path", None),
        )


@dataclass
class SnipConfig:
    nodes: dict[str, NodeConfig]
    defaults: Defaults

    @classmethod
    def from_json(cls, flake_ref: str, data: dict) -> SnipConfig:
        defaults = Defaults.from_json(data.get("defaults", {}))
        nodes = {}
        for name, node_data in data.get("nodes", {}).items():
            nodes[name] = NodeConfig.from_json(
                flake_ref, name, node_data, defaults.nodes
            )
        return cls(nodes=nodes, defaults=defaults)
