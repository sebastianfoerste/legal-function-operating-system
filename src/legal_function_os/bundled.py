"""Locate the synthetic data shipped inside the package, and read the text files a
command is given.

The demo data lives under the package rather than at the repository root so an
installed wheel carries it. That lets a reviewer run the demo without cloning:

    uvx --from git+https://github.com/sebastianfoerste/legal-function-operating-system \\
      legal-function-os
"""

from __future__ import annotations

import codecs
from importlib import resources
from pathlib import Path

DATA_PACKAGE = "legal_function_os.data"


def decode_utf8(data: bytes) -> str:
    """UTF-8 text with an optional byte order mark. A UnicodeDecodeError counts its
    position from the first byte of ``data``, the mark included, as an editor shows it."""

    mark = len(codecs.BOM_UTF8) if data.startswith(codecs.BOM_UTF8) else 0
    try:
        return data[mark:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnicodeDecodeError(exc.encoding, data, exc.start + mark, exc.end + mark, exc.reason) from None


def read_utf8(path: str | Path) -> str:
    """A text file a command was given (see ``decode_utf8``). Raises OSError when it
    cannot be read and UnicodeDecodeError when it is not UTF-8."""

    return decode_utf8(Path(path).read_bytes())


def not_utf8(exc: UnicodeDecodeError) -> str:
    """Why a file could not be read as text, said the same way by every command."""

    return f"it is not UTF-8 text (byte {exc.object[exc.start]:#04x} at position {exc.start}); save it as UTF-8"


def bundled_path(name: str) -> Path:
    """Return the on-disk path of a bundled synthetic data file."""
    resource = resources.files(DATA_PACKAGE).joinpath(name)
    if not resource.is_file():
        raise FileNotFoundError(f"bundled data file is missing: {name}")
    return Path(str(resource))
