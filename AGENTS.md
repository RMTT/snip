# AGENTS.md

## Project

snip — a NixOS deployment tool. Reads node config from `outputs.snip` in `flake.nix`, builds closures, copies to remotes, and activates them with an ANSI TUI.

## Commands

```bash
# Install dependencies
uv sync

# Run CLI
uv run snip --help

# Tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run ty check src/
```

## Architecture

```
src/snip/
├── models.py    # Defaults, NodeConfig, SnipConfig dataclasses (JSON → Python)
├── utils.py     # BoundedList, async run/run_streaming subprocess helpers
├── nix.py       # nix eval/build/copy wrappers (uses utils.run)
├── ssh.py       # SSH activation via host ssh command, auto-sudo for non-root users (uses utils.run)
├── ui.py        # DeployPhase enum, NodeProgress, ANSI rendering
├── deploy.py    # async deploy orchestrator (build → copy → activate)
└── cli.py       # argparse CLI entry point
```

**Data flow:** `nix eval --json '.#snip'` → `SnipConfig.from_json()` → for each node: `nix build` → `nix copy` → `ssh activate` (with `sudo` if user is not `root`)

## Conventions

- Python 3.12+, zero runtime dependencies
- All SSH uses the host's `ssh` binary via subprocess (no SSH libraries)
- Type annotations required on all public functions in `src/`
- Lint rules: `E`, `F`, `I`, `UP`, `ANN` (ANN ignored in tests)
- Line length: 88 (ruff default)
- No comments unless requested

## Before Committing

Run all checks:

```bash
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run ty check src/ && uv run pytest tests/ -v
```

All must pass.
