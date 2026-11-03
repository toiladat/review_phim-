"""Condense the source SRT into compact time-stamped blocks for script writing."""
import re, sys, json, os

SRC = sys.argv[1] if len(sys.argv) > 1 else r"d:\final_I2V\review_tool\1.srt"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"d:\final_I2V\review_tool\work\srt_condensed.txt"


def t2s(t):
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(path):
    txt = open(path, encoding="utf-8-sig").read()
    blocks = re.split(r"\r?\n\r?\n", txt.strip())
    subs = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        m = re.match(r"(\S+)\s*-->\s*(\S+)", lines[1])
        if not m:
            continue
        subs.append((t2s(m.group(1)), t2s(m.group(2)), " ".join(lines[2:]).strip()))
    return subs


def fmt(s):
    s = int(s)
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


if __name__ == "__main__":
    subs = parse(SRC)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    groups = []
    cur = None
    for st, en, tx in subs:
        if cur and st - cur[1] <= 1.5 and en - cur[0] < 20:
            cur[1] = en
            cur[2].append(tx)
        else:
            if cur:
                groups.append(cur)
            cur = [st, en, [tx]]
    groups.append(cur)
    with open(OUT, "w", encoding="utf-8") as f:
        for st, en, txs in groups:
            f.write(f"[{fmt(st)}] {'，'.join(txs)}\n")
    json.dump(subs, open(OUT.replace(".txt", ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(len(subs), "subs ->", len(groups), "groups")

