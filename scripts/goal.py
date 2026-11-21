"""Run the repository's acceptance goal, optionally starting Docker Compose."""

import argparse
import shutil
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
    npm = shutil.which("npm")
    if not npm:
        parser.error("验收需要 Node.js 22.12+ 与 npm，用于检查 TypeScript 并构建 Vue 页面。")
    web = str(ROOT / "src" / "web")
    commands = [
        [npm, "--prefix", web, "ci", "--no-audit", "--no-fund"],
        [npm, "--prefix", web, "run", "build"],
        [sys.executable, "-m", "pytest", "-q", "tests"],
        [sys.executable, "-m", "tests.browser_smoke"],
        ["docker", "compose", "config", "--quiet"],
    ]
    if args.docker:
        commands.insert(0, ["docker", "compose", "up", "-d", "--wait", "db"])
        commands.append(["docker", "compose", "up", "-d", "--build", "--wait"])
    for cmd in commands:
        print(">", " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, cwd=ROOT)
    print("All requested acceptance steps passed.")


if __name__ == "__main__":
    main()
