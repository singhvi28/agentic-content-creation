#!/usr/bin/env python3
"""Run Alembic migrations to head. Prefer this over API-boot migrations."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")
    print("Migrations applied: head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
