#!/usr/bin/env python3
# Bootstrap: reassemble worker from parts (pushed in chunks due to size limits)
from pathlib import Path
import sys
base = Path(__file__).resolve().parent
parts = sorted(base.glob("_wpart_*.txt"))
if not parts:
    print("Worker parts missing", flush=True)
    sys.exit(1)
code = "".join(p.read_text() for p in parts)
exec(compile(code, str(base / "main.py"), "exec"), {"__name__": "__main__", "__file__": str(base / "main.py")})
