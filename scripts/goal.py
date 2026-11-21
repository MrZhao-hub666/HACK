"""Run the repository's acceptance goal, optionally starting Docker Compose."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docker", action="store_true", help="build and start the Compose deployment"
    )
    args = parser.parse_args()
    commands = [
        [sys.executable, "-m", "pytest", "-q", "tests"],
        [sys.executable, "-m", "tests.browser_smoke"],
        ["docker", "compose", "config", "--quiet"],
    ]
    if args.docker:
        commands.append(["docker", "compose", "up", "-d", "--build", "--wait"])
    for cmd in commands:
        print(">", " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, cwd=ROOT)
    print("All requested acceptance steps passed.")


if __name__ == "__main__":
    main()
