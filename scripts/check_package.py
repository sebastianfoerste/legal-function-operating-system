#!/usr/bin/env python3
"""Build the wheel, install it into a clean virtual environment and run it there.

The demo, the tests and `make check` all run from the checkout, where a data file
missing from the package data or a broken entry point would go unnoticed. This
check builds the wheel from a copy of the project, confirms every module and
bundled data file is inside it, installs it into a fresh virtual environment and
runs the console scripts from a directory outside the checkout.

Building needs network access once, for pip to fetch setuptools.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "legal_function_os"
BUILD_INPUTS = ("pyproject.toml", "README.md", "LICENSE", "src")

# (console script, arguments) run from the clean environment.
SMOKE_RUNS: tuple[tuple[str, ...], ...] = (
    ("legal-function-os", "--version"),
    ("legal-function-os", "--quiet"),
    ("raas-deal-desk", "--quiet"),
)


def expected_files() -> set[str]:
    """Every module and bundled data file the wheel must carry."""

    modules = {
        f"legal_function_os/{path.relative_to(PACKAGE).as_posix()}"
        for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    data = {f"legal_function_os/data/{path.name}" for path in (PACKAGE / "data").glob("*.json")}
    return modules | data


def run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def build_wheel(workdir: Path) -> Path:
    project = workdir / "project"
    project.mkdir()
    for name in BUILD_INPUTS:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(
                source, project / name, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info")
            )
        else:
            shutil.copy2(source, project / name)
    dist = workdir / "dist"
    run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(dist), str(project)],
        cwd=workdir,
    )
    wheels = sorted(dist.glob("legal_function_os-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel in {dist}, found {[w.name for w in wheels]}")
    return wheels[0]


def check_contents(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    return sorted(expected_files() - names)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        wheel = build_wheel(workdir)
        missing = check_contents(wheel)
        if missing:
            print(f"{wheel.name} is missing: {', '.join(missing)}")
            return 1

        env_dir = workdir / "venv"
        venv.create(env_dir, with_pip=True)
        bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
        python = str(bin_dir / "python")
        run([python, "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], cwd=workdir)

        outside = workdir / "elsewhere"
        outside.mkdir()
        location = run(
            [python, "-c", "import legal_function_os; print(legal_function_os.__file__)"],
            cwd=outside,
        ).strip()
        if str(ROOT) in location:
            print(f"imported the checkout instead of the installed wheel: {location}")
            return 1
        for script, *arguments in SMOKE_RUNS:
            run([str(bin_dir / script), *arguments], cwd=outside)

    runs = ", ".join(" ".join(command) for command in SMOKE_RUNS)
    print(f"package check passed: {wheel.name} carries {len(expected_files())} files; ran {runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
