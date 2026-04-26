"""Q13 compliant — subprocess.run with list args, no shell=True."""
import subprocess

def run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode
