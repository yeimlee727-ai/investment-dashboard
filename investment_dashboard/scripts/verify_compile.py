from __future__ import annotations

import compileall
from pathlib import Path
import re


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    exclude = re.compile(r"(\\.venv|__pycache__|\\.pytest_cache|\\.ruff_cache|db)")
    return (
        0
        if compileall.compile_dir(project_root, quiet=1, force=True, rx=exclude)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
