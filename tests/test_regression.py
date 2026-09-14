import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_existing_tools_and_paper_record_report_version() -> None:
    versions = set()
    for name in ("nosleep", "after", "pourover", "paper-record"):
        completed = subprocess.run(
            [str(ROOT / "bin" / name), "--version"],
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert name in completed.stdout
        assert "1.4.0" in completed.stdout
        versions.add(completed.stdout.strip().split()[-1])
    assert len(versions) == 1


def test_install_script_still_links_every_bin_tool_without_executing_privileged_steps() -> None:
    completed = subprocess.run(
        ["bash", "-n", str(ROOT / "install.sh")], capture_output=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "for tool in bin/*" in script
    assert 'ln -sf "$PWD/$tool"' in script
    assert (ROOT / "bin" / "paper-record").stat().st_mode & 0o111
