"""Test entry: run apply.py against a sandbox root with the srcds gate stubbed (sandbox has no srcds)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apply as A  # noqa: E402

A.srcds_running = lambda root: False
args = sys.argv[1:]
root = args[0]
assert "sandbox_server" in root, "test entry only runs against the sandbox"
fail = int(args[args.index("--fail-after") + 1]) if "--fail-after" in args else None
sys.exit(A.apply(root, False, fail))
