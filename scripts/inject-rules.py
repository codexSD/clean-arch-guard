#!/usr/bin/env python3
"""Emits the always-on architecture rules into the session context at start.

Skips injection in repos that opt out with .no-arch-guard at the project root.
"""
import os
import sys
from pathlib import Path

project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())

if (project_dir / ".no-arch-guard").is_file():
    sys.exit(0)

plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    print("clean-arch-guard: CLAUDE_PLUGIN_ROOT is unset", file=sys.stderr)
    sys.exit(1)

rules = Path(plugin_root) / "rules" / "always-on.md"
try:
    sys.stdout.write(rules.read_text(encoding="utf-8"))
except OSError as err:
    print(f"clean-arch-guard: cannot read {rules}: {err}", file=sys.stderr)
    sys.exit(1)
