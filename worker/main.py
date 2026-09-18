#!/usr/bin/env python3
import base64, sys
from pathlib import Path
base = Path(__file__).resolve().parent
parts = sorted(base.glob("_b64_*.txt"))
if not parts:
    print("missing b64 parts", flush=True); sys.exit(1)
code = base64.b64decode("".join(p.read_text().strip() for p in parts))
exec(compile(code, str(base/"main.py"), "exec"), {"__name__":"__main__","__file__":str(base/"main.py")})
