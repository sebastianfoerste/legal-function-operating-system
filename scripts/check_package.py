#!/usr/bin/env python3
"""Build the wheel, install it into a clean virtual environment and run it there.

The demo, the tests and `make check` all run from the checkout, where a data file
missing from the package data or a broken entry point would go unnoticed. This
check builds the wheel from a copy of the project, confirms every module and
bundled data file is inside it and that it declares every console script, installs
it into a fresh virtual environment, imports the MCP server module there (no extra
needed for the import) and runs the console scripts from a directory outside the
checkout. It then builds the sdist and runs a pinned ``twine check --strict`` on
both distributions.

Building needs network access once, for pip to fetch setuptools, build and twine.
"""

from __future__ import annotations

import configparser
import io
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

# (console script, arguments) run from the clean environment. The MCP server's
# ``--help`` exits before it imports the optional extra.
SMOKE_RUNS: tuple[tuple[str, ...], ...] = (
    ("legal-function-os", "--version"),
    ("legal-function-os", "--quiet"),
    ("raas-deal-desk", "--quiet"),
    ("legal-function-os-mcp", "--help"),
)
CONSOLE_SCRIPTS = ("legal-function-os", "raas-deal-desk", "legal-function-os-mcp")
# Pinned so the check does not change under a new release; release.yml builds with
# the same build version.
RELEASE_TOOLS = ("build==1.6.1", "twine==7.0.0")


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


def missing_console_scripts(wheel: Path) -> list[str]:
    """The console scripts the wheel's entry_points.txt does not declare."""

    with zipfile.ZipFile(wheel) as archive:
        entry_points = [name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")]
        if len(entry_points) != 1:
            return list(CONSOLE_SCRIPTS)
        parser = configparser.ConfigParser()
        parser.read_file(io.StringIO(archive.read(entry_points[0]).decode("utf-8")))
    declared = set(parser["console_scripts"]) if parser.has_section("console_scripts") else set()
    return [script for script in CONSOLE_SCRIPTS if script not in declared]


def check_distributions(workdir: Path, python: str) -> Path:
    """Build the sdist next to the wheel and run twine's strict metadata check on both."""

    run([python, "-m", "pip", "install", "--quiet", *RELEASE_TOOLS], cwd=workdir)
    dist = workdir / "dist"
    run([python, "-m", "build", "--sdist", "--outdir", str(dist), str(workdir / "project")], cwd=workdir)
    sdists = sorted(dist.glob("legal_function_os-*.tar.gz"))
    if len(sdists) != 1:
        raise SystemExit(f"expected one sdist in {dist}, found {[s.name for s in sdists]}")
    run([python, "-m", "twine", "check", "--strict", *(str(path) for path in sorted(dist.iterdir()))], cwd=workdir)
    return sdists[0]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        wheel = build_wheel(workdir)
        missing = check_contents(wheel)
        if missing:
            print(f"{wheel.name} is missing: {', '.join(missing)}")
            return 1
        undeclared = missing_console_scripts(wheel)
        if undeclared:
            print(f"{wheel.name} does not declare the console scripts: {', '.join(undeclared)}")
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
        # The MCP server module imports without the optional extra; only the server start needs it.
        run([python, "-c", "import legal_function_os.mcp_server as server; print(server.__name__)"], cwd=outside)
        for script, *arguments in SMOKE_RUNS:
            run([str(bin_dir / script), *arguments], cwd=outside)
        sdist = check_distributions(workdir, python)

    runs = ", ".join(" ".join(command) for command in SMOKE_RUNS)
    print(
        f"package check passed: {wheel.name} carries {len(expected_files())} files and declares "
        f"{', '.join(CONSOLE_SCRIPTS)}; imported legal_function_os.mcp_server; ran {runs}; "
        f"twine check --strict passed on {wheel.name} and {sdist.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
