"""Locate the synthetic data shipped inside the package.

The demo data lives under the package rather than at the repository root so an
installed wheel carries it. That lets a reviewer run the demo without cloning:

    uvx --from git+https://github.com/sebastianfoerste/legal-function-operating-system \\
      legal-function-os
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

DATA_PACKAGE = "legal_function_os.data"


def bundled_path(name: str) -> Path:
    """Return the on-disk path of a bundled synthetic data file."""
    resource = resources.files(DATA_PACKAGE).joinpath(name)
    if not resource.is_file():
        raise FileNotFoundError(f"bundled data file is missing: {name}")
    return Path(str(resource))
