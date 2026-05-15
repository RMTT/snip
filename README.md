# snip

A simple NixOS deployment tool that reads node configuration from `flake.nix` and deploys in parallel with an ANSI TUI.

## Features

- **Flake-native** — reads from `outputs.snip` in your `flake.nix`
- **Parallel deployment** — deploy multiple nodes concurrently
- **ANSI TUI** — live progress bars, phase tracking, activation output streaming
- **Local and remote builds** — build locally or on the target machine

## Example output

```plain
> uv run snip --flake ../flakes deploy --parallel 1 mtspc cn2-box 
✅ Evaluating flake: ../flakes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
snip deploy » deploying
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
● host-A         │ pushing  ·······················━━━━━━·
 ↳ Using saved setting for 'extra-trusted-public-keys = noctalia.cachix.org-1:pCOR47nnMEo5thcxNDtzWpOxNFQsBRglJzxWPp3dkU4= nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCW...
 ↳ pushing ../flakes#nixosConfigurations.cn2-box to cn2-box.rmtt.host
● host-B         │ queued   ·······················━━━━━━·
 ↳ preparing

```
## Configuration

Add a `snip` output to your `flake.nix`:

```nix
{
  outputs = { ... }: {
    nixosConfigurations = {
      web-server = ...;
      db-server = ...;
    };

    snip = {
      defaults.nodes = {
        user = "root";
        port = 22;
        remoteBuild = false;
      };

      nodes = {
        web-server.host = "web.example.com";
        db-server = {
          host = "10.0.0.5";
          user = "deploy";
          remoteBuild = true;
        };
      };
    };
  };
}
```

### Node fields

| Field | Default | Description |
|---|---|---|
| `host` | node name | SSH target hostname/IP |
| `user` | from defaults | SSH user |
| `port` | from defaults | SSH port |
| `sshOptions` | `[]` | Extra SSH options |
| `remoteBuild` | from defaults | Build on target instead of locally |
| `config` | `nixosConfigurations.<name>` | Nix attribute path |

## Usage

```bash
# Deploy all nodes
snip deploy

# Deploy specific nodes
snip deploy web-server db-server

# Filter by glob pattern
snip deploy 'web-*'

# Force remote builds
snip deploy --remote-build

# Dry run
snip deploy --dry-run

# List nodes
snip list

# Limit parallelism
snip deploy --parallel 2

# Specify a different flake
snip --flake /path/to/flake deploy
```

## Install

```bash
git clone <repo-url> && cd snip
uv sync
uv run snip --help
```

Requires Nix with flake support on the deploying machine.

## Dependencies

- Python 3.12+, zero runtime dependencies
- Nix with flake support
