"""Condense the source SRT into compact time-stamped blocks for script writing."""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_input(ext, default_name):
    inp_dir = os.path.join(ROOT, "input")
    p1 = os.path.join(inp_dir, default_name)
    if os.path.exists(p1):
        return p1
    cands = sorted(glob.glob(os.path.join(inp_dir, f"*.{ext}")))
    if cands:
        return cands[0]
    return os.path.join(ROOT, default_name)


SRC = sys.argv[1] if len(sys.argv) > 1 else find_input("srt", "1.srt")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "work", "srt_condensed.txt")


def t2s(t):
    h, m, rest = t.split(":")
    s, ms = rest.strip().replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(path):
    txt = open(path, encoding="utf-8-sig", errors="replace").read()
    blocks = re.split(r"\r?\n\r?\n", txt.strip())
    subs = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 2:
            continue
        tline = lines[1] if lines[0].strip().isdigit() else lines[0]
        body = lines[2:] if lines[0].strip().isdigit() else lines[1:]
        m = re.match(r"(\S+)\s*-->\s*(\S+)", tline)
        if not m or not body:
            continue
        subs.append((t2s(m.group(1)), t2s(m.group(2)), " ".join(body).strip()))
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
    if cur:
        groups.append(cur)
    with open(OUT, "w", encoding="utf-8") as f:
        for st, en, txs in groups:
            f.write(f"[{fmt(st)}] {'，'.join(txs)}\n")
    json.dump(subs, open(OUT.replace(".txt", ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"source SRT: {SRC} -> {len(subs)} subs -> {len(groups)} groups")
