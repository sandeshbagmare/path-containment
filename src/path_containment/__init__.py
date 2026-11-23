"""Keep paths inside a directory.

Untrusted path fragments arrive from archive members, uploaded file names and URL
parameters. Joining them with ``Path`` is not enough: ``os.path.join("uploads", "../
/etc/passwd")`` hands back a path outside the directory, and a symlink inside it can
point anywhere as well.

    >>> from pathlib import Path
    >>> from path_containment import safe_join
    >>> safe_join(Path.cwd() / "uploads", "report.txt").name
    'report.txt'
    >>> safe_join("uploads", "../etc/passwd")
    Traceback (most recent call last):
    path_containment.UnsafePathError: parent directory in path component: '../etc/passwd'

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

__all__ = [
    "UnsafePathError",
    "is_within",
    "safe_join",
    "safe_member_name",
    "safe_target",
    "sanitize_filename",
]

__version__ = "0.1.0"

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_ILLEGAL = re.compile(r'[<>:"/\\|?*]')
_TRAILING_JUNK = re.compile(r"[ .]+$")
_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)


class UnsafePathError(ValueError):
    """A path that would leave the directory it is supposed to stay in."""


def is_within(base: str | os.PathLike[str], path: str | os.PathLike[str]) -> bool:
    """True when ``path`` is ``base`` or inside it, with symlinks resolved."""
    base_path = Path(base).resolve()
    try:
        candidate = Path(path).resolve()
    except OSError:  # pragma: no cover - broken symlink loops and the like
        return False
    return candidate == base_path or base_path in candidate.parents


def _reject_fragment(fragment: str) -> None:
    if _CONTROL.search(fragment):
        raise UnsafePathError(f"control character in path component: {fragment!r}")
    # ntpath.isabs("/etc/passwd") is False (no drive), so check the separator too.
    if os.path.isabs(fragment) or _DRIVE.match(fragment) or fragment.startswith(("/", "\\")):
        raise UnsafePathError(f"absolute path component: {fragment!r}")
    parts = PurePosixPath(fragment.replace("\\", "/")).parts
    if ".." in parts:
        raise UnsafePathError(f"parent directory in path component: {fragment!r}")


def safe_join(base: str | os.PathLike[str], *parts: str | os.PathLike[str]) -> Path:
    """Join ``parts`` onto ``base`` and refuse anything that leaves it.

    The result is resolved, so a symlink that points outside ``base`` is rejected
    rather than followed.
    """
    for part in parts:
        text = os.fspath(part)
        if text in ("", "."):
            continue
        _reject_fragment(text)
    root = Path(base).resolve()
    candidate = root
    for part in parts:
        candidate = candidate / os.fspath(part)
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise UnsafePathError(f"{resolved} is outside {root}")
    return resolved


def safe_member_name(name: str) -> str:
    """Normalise an archive member name into a relative POSIX path, or refuse it.

    ``"./docs/a.txt"`` becomes ``"docs/a.txt"``; ``"../a"``, ``"/etc/passwd"`` and
    ``"C:\\a"`` raise :class:`UnsafePathError`.
    """
    text = name.replace("\\", "/").strip()
    if not text:
        raise UnsafePathError("empty archive member name")
    _reject_fragment(text)
    normalised = str(PurePosixPath(text))
    if normalised in ("", "."):
        raise UnsafePathError(f"archive member names nothing: {name!r}")
    return normalised


def safe_target(base: str | os.PathLike[str], member: str) -> Path:
    """Where an archive member may be written inside ``base``."""
    return safe_join(base, *safe_member_name(member).split("/"))


def sanitize_filename(
    name: str,
    *,
    replacement: str = "_",
    max_length: int = 255,
) -> str:
    """Turn arbitrary text into a file name that is safe on every platform.

    Removes control characters, path separators and the characters Windows forbids,
    trims trailing dots and spaces, avoids the reserved device names (``CON``,
    ``NUL``, ``COM1`` …) and shortens the result. Unicode is preserved.
    """
    if max_length < 1:
        raise ValueError("max_length must be positive")
    text = _CONTROL.sub(replacement, name)
    text = _WINDOWS_ILLEGAL.sub(replacement, text)
    text = text.strip().strip(".").strip()
    text = _TRAILING_JUNK.sub("", text)
    if not text:
        return replacement[:max_length] or "_"
    stem = text.split(".", 1)[0].lower()
    if stem in _RESERVED_NAMES:
        text = f"{replacement}{text}"
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    return text or replacement[:max_length]
