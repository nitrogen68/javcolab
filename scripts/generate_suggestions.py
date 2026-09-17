#!/usr/bin/env python3
"""Ekstrak saran pencarian dari dump MySQL (javdb.sql) ke data/suggestions.json."""
import json
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "javdb.sql"
LIMIT = 500

def main():
    data = open(SRC, encoding="utf-8", errors="ignore").read()
    marker = "INSERT INTO `search_logs`"
    starts = [m.start() for m in re.finditer(re.escape(marker), data)]
    rows = []
    for s in starts:
        e = s + len(marker)
        semi = data.find(";", e)
        block = data[e:semi + 1]
        for tup in re.finditer(r"\(([^)]*)\)\s*(?:,|;)", block):
            fields = tup.group(1)
            parts, cur, in_q = [], "", False
            for ch in fields:
                if ch == "'":
                    in_q = not in_q; cur += ch
                elif ch == "," and not in_q:
                    parts.append(cur); cur = ""
                else:
                    cur += ch
            parts.append(cur)
            get = lambda i: parts[i].strip().strip("'") if len(parts) > i else ""
            vid = get(0)
            if vid:
                rows.append((vid, get(1)[:90], get(4), get(5)))
    seen, uniq = set(), []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0]); uniq.append(r)
    out = [{"id": a, "title": b, "url": c, "thumb": d} for a, b, c, d in uniq[:LIMIT]]
    with open("data/suggestions.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"OK: {len(out)} saran disimpan (dari {len(rows)} baris, {len(uniq)} unik).")

if __name__ == "__main__":
    main()