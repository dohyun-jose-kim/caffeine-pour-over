"""Three-layer scientific paper records."""

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


try:
    __version__ = version("caffeine-paper-record")
except PackageNotFoundError:
    __version__ = (Path(__file__).parents[2] / "VERSION").read_text(encoding="utf-8").strip()


def display_version() -> str:
    """Match the repository tools' +dev.<sha> display outside an exact release tag."""
    root = Path(__file__).parents[2]
    if not (root / ".git").exists():
        return __version__
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    tagged = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "describe",
            "--exact-match",
            "--match",
            f"v{__version__}",
            "HEAD",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if sha.returncode == 0 and tagged.returncode != 0:
        return f"{__version__}+dev.{sha.stdout.strip()}"
    return __version__
