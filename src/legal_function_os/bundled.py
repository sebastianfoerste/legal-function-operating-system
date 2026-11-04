"""Locate the synthetic data shipped inside the package, and word a file a command
cannot decode.

The demo data lives under the package rather than at the repository root so an
installed wheel carries it. That lets a reviewer run the demo without cloning:

    uvx --from git+https://github.com/sebastianfoerste/legal-function-operating-system \\
      legal-function-os
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

DATA_PACKAGE = "legal_function_os.data"


def not_utf8(exc: UnicodeDecodeError) -> str:
    """Why a file could not be read as text, said the same way by every command."""

    return f"it is not UTF-8 text (byte {exc.object[exc.start]:#04x} at position {exc.start}); save it as UTF-8"


def bundled_path(name: str) -> Path:
    """Return the on-disk path of a bundled synthetic data file."""
    resource = resources.files(DATA_PACKAGE).joinpath(name)
    if not resource.is_file():
        raise FileNotFoundError(f"bundled data file is missing: {name}")
    return Path(str(resource))
