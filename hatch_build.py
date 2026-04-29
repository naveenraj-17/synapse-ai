import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Auto-build the Next.js frontend before packaging if not already built."""

    def initialize(self, version, build_data):
        root = Path(self.root)
        bundled = root / "synapse" / "_frontend"
        if bundled.exists():
            return

        print("synapse/_frontend/ not found — building Next.js frontend...")
        script = root / "scripts" / "build_frontend.sh"
        result = subprocess.run(["bash", str(script)], cwd=root)
        if result.returncode != 0:
            print("Error: frontend build failed. Cannot package without it.", file=sys.stderr)
            sys.exit(1)
