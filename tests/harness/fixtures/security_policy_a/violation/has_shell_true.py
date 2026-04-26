"""Q13 violation — subprocess.run with shell=True banned."""
import subprocess

def run(cmd: str) -> int:
    return subprocess.run(cmd, shell=True).returncode
