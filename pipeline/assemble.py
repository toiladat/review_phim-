# -*- coding: utf-8 -*-
"""Assemble the Vietnamese review video.

Stages (cached in work/):
  audio  : trim TTS mp3 -> wav, measure durations
  plan   : choose source segments for each beat (shot-aware, avoids repeats & "to be continued" cards)
  beats  : render one mp4 per beat (zoom, blur hard-sub band, original audio ducked)
  final  : concat beats, build narration track, burn Vietnamese ASS subtitles, mix, export
"""
import json, math, os, re, subprocess, sys, wave

sys.path.insert(0, os.path.dirname(__file__))
from script_beats import BEATS, TITLE

ROOT = r"d:\final_I2V\review_tool"
SRC = os.path.join(ROOT, "1.mp4")
WORK = os.path.join(ROOT, "work")
FF = os.path.join(ROOT, "tools", "ffmpeg.exe")
TTS_DIR = os.path.join(WORK, "tts", "narration")
AUD = os.path.join(WORK, "aud")
SEG = os.path.join(WORK, "beats")
OUT = os.path.join(ROOT, "output")
FPS_NUM, FPS_DEN = 30000, 1001
FPS = FPS_NUM / FPS_DEN
PAUSE = 0.14          # silence between beats (s)
SEG_TARGET = 2.9      # preferred visual segment length (s)
ORIG_VOL = 0.13       # original soundtrack volume under narration
W, H = 1080, 1920
ZOOM = 1.05
BAND_Y, BAND_H = 1215, 430   # blurred band covering burned-in Chinese subs (after zoom)
for d in (AUD, SEG, OUT):
    os.makedirs(d, exist_ok=True)


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("CMD FAILED:", " ".join(cmd)[:2000])
        print(r.stderr[-3000:])
        raise SystemExit(1)
    return r


def ts(s):
    m = re.match(r"(\d+):(\d+)", s.strip())
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_windows(spec):
    out = []
    for part in spec.split(","):
        a, b = part.split("-")
        out.append((float(ts(a)), float(ts(b))))
    return out


def wav_dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- audio
def stage_audio():
    info = []
    for i in range(len(BEATS)):
        src = os.path.join(TTS_DIR, f"{i + 1}.mp3")
        dst = os.path.join(AUD, f"{i + 1:03d}.wav")
        if not os.path.exists(src):
            raise SystemExit(f"missing TTS {src}")
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            # trim leading/trailing silence ("remove air")
            af = ("silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.03,"
                  "areverse,silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.06,areverse")
            run([FF, "-y", "-i", src, "-af", af, "-ar", "48000", "-ac", "1", dst])
        info.append({"i": i, "wav": dst, "dur": round(wav_dur(dst), 3)})
    json.dump(info, open(os.path.join(WORK, "beats_audio.json"), "w"), indent=1)
    tot = sum(x["dur"] for x in info) + PAUSE * len(info)
    print(f"audio: {len(info)} beats, total {tot / 60:.2f} min")
    return info


# ---------------------------------------------------------------- plan
def load_exclusions():
    subs = json.load(open(os.path.join(WORK, "srt_condensed.json"), encoding="utf-8"))
    ex = []
    for st, en, tx in subs:
        if "待续" in tx or "剧终" in tx or "待" in tx and "续" in tx:
            ex.append((st - 1.6, en + 1.2))
    return ex


def subtract(intervals, cuts):
    res = []
    for a, b in intervals:
        segs = [(a, b)]
        for c, d in cuts:
            nxt = []
            for x, y in segs:
                if d <= x or c >= y:
                    nxt.append((x, y))
                else:
                    if c > x:
                        nxt.append((x, c))
                    if d < y:
                        nxt.append((d, y))
            segs = nxt
        res.extend(segs)
    return res


def pieces_for(windows, shots, excl, used, min_len=1.0):
    out = []
    for wa, wb in windows:
        for sa, sb in shots:
            a, b = max(sa + 0.07, wa), min(sb - 0.07, wb)
            if b - a >= min_len:
                out.append((a, b))
    out = subtract(out, excl)
    out = [p for p in out if p[1] - p[0] >= min_len]
    fresh = [p for p in subtract(out, used) if p[1] - p[0] >= min_len]
    return out, fresh


def choose(pieces, D, seg_max=3.6):
    """Pick segments (a, b, speed) from ordered pieces to fill D seconds.
    Spread picks evenly over the window so the visuals follow the story progression."""
    L = sum(b - a for a, b in pieces)
    if L <= 0:
        return None
    if L <= D * 1.02:
        speed = max(L / D, 0.62)
        segs = [(a, b, speed) for a, b in pieces]
        got = L / speed
        k = 0
        while got < D - 0.02:  # still short -> reuse pieces again (rare)
            a, b = pieces[k % len(pieces)]
            segs.append((a, b, speed))
            got += (b - a) / speed
            k += 1
        return segs
    # split long pieces into sub-pieces of <= seg_max so pacing stays lively
    subs = []
    for a, b in pieces:
        n = max(1, math.ceil((b - a) / (seg_max + 1.0)))
        step = (b - a) / n
        for j in range(n):
            subs.append((a + j * step, a + (j + 1) * step))
    caps = [min(b - a, seg_max) for a, b in subs]
    pick = None
    for k in range(1, len(subs) + 1):
        idx = sorted(set(round((j + 0.5) * len(subs) / k - 0.5) for j in range(k)))
        if sum(caps[i] for i in idx) >= D:
            pick = idx
            break
    if pick is None:  # need the full lengths
        pick = list(range(len(subs)))
        caps = [b - a for a, b in subs]
    lens = [caps[i] for i in pick]
    excess = sum(lens) - D
    # trim excess proportionally, keep >= 0.9 s
    while excess > 1e-3:
        room = [max(l - 0.9, 0) for l in lens]
        tr = sum(room)
        if tr <= 1e-6:
            break
        f = min(1.0, excess / tr)
        lens = [l - r * f for l, r in zip(lens, room)]
        excess = sum(lens) - D
    segs = []
    for i, l in zip(pick, lens):
        a, b = subs[i]
        mid = (a + b) / 2
        s = max(a, mid - l / 2)
        segs.append((s, min(b, s + l), 1.0))
    tot = sum(e - s for s, e, _ in segs)
    if tot < D - 0.02:
        sp = max(tot / D, 0.62)
        segs = [(s, e, sp) for s, e, _ in segs]
    return segs


def stage_plan(info):
    shots = json.load(open(os.path.join(WORK, "shots.json")))
    flags_p = os.path.join(WORK, "shot_flags.json")
    clean = shots
    if os.path.exists(flags_p):
        flags = json.load(open(flags_p))
        clean = [s for s, f in zip(shots, flags) if not any(x[0] >= 1500 for x in f)]
        print(f"shots: {len(shots)}, without overlay text: {len(clean)}")
    excl = load_exclusions()
    used = []
    plan = []
    for (spec, text), ai in zip(BEATS, info):
        D = ai["dur"] + PAUSE
        nfr = round(D * FPS)
        D = nfr / FPS
        windows = parse_windows(spec)
        allc, freshc = pieces_for(windows, clean, excl, used)
        alls, fresh_s = pieces_for(windows, shots, excl, used)
        tot = lambda ps: sum(b - a for a, b in ps)
        for cand in (freshc, allc, fresh_s, alls):
            if tot(cand) >= D * 0.75:
                use = cand
                break
        else:
            use = max((freshc, allc, fresh_s, alls), key=tot)
        segs = choose(use, D)
        if not segs:
            raise SystemExit(f"no visuals for beat {ai['i'] + 1}: {spec}")
        used.extend((a, b) for a, b, _ in segs)
        plan.append({"i": ai["i"], "dur": D, "frames": nfr, "wav": ai["wav"], "audio_dur": ai["dur"],
                     "text": text, "segs": segs})
    json.dump(plan, open(os.path.join(WORK, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    slow = [p["i"] + 1 for p in plan if any(s[2] < 0.95 for s in p["segs"])]
    print(f"plan ok; beats with slow-motion fill: {slow}")
    return plan


# ---------------------------------------------------------------- render beats
def vchain():
    zw, zh = round(W * ZOOM / 2) * 2, round(H * ZOOM / 2) * 2
    return (f"scale={zw}:{zh}:flags=lanczos,crop={W}:{H}:{(zw - W) // 2}:{(zh - H) // 2},setsar=1")


def render_beat(p, force=False):
    out = os.path.join(SEG, f"{p['i'] + 1:03d}.mp4")
    sig = json.dumps([p["segs"], p["frames"], BAND_Y, BAND_H, ZOOM, ORIG_VOL])
    sigf = out + ".sig"
    if not force and os.path.exists(out) and os.path.exists(sigf) and open(sigf).read() == sig:
        return out
    cmd = [FF, "-y", "-hide_banner", "-loglevel", "error"]
    fc = []
    for k, (a, b, sp) in enumerate(p["segs"]):
        cmd += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", SRC]
        vf = f"[{k}:v]{vchain()},fps={FPS_NUM}/{FPS_DEN}"
        af = f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo"
        if sp < 0.999:
            vf += f",setpts=PTS/{sp:.4f}"
            af += f",atempo={max(sp, 0.5):.4f}"
        fc.append(vf + f",setpts=PTS-STARTPTS[v{k}]")
        fc.append(af + f",asetpts=PTS-STARTPTS[a{k}]")
    n = len(p["segs"])
    cmd += ["-loop", "1", "-i", os.path.join(WORK, "band_mask.png")]
    fc.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    # blur the burned-in Chinese subtitle band (feathered edges via alpha mask)
    fc.append(f"[{n}:v]format=gray,scale={W}:{BAND_H}[mk]")
    fc.append(f"[vc]split[vb][vt];[vt]crop={W}:{BAND_H}:0:{BAND_Y},boxblur=luma_radius=42:luma_power=3:chroma_radius=20:chroma_power=2,"
              f"eq=brightness=-0.10:saturation=0.75,format=yuva420p[bl0];[bl0][mk]alphamerge[bl];"
              f"[vb][bl]overlay=0:{BAND_Y}:shortest=1,tpad=stop_mode=clone:stop_duration=2,format=yuv420p[vo]")
    fc.append(f"[ac]volume={ORIG_VOL},apad[ao]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]",
            "-frames:v", str(p["frames"]), "-t", f"{p['dur']:.4f}", "-r", f"{FPS_NUM}/{FPS_DEN}",
            "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-g", "60",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", out]
    run(cmd)
    open(sigf, "w").write(sig)
    return out


def stage_beats(plan, only=None):
    from concurrent.futures import ThreadPoolExecutor
    todo = [p for p in plan if only is None or p["i"] + 1 in only]
    with ThreadPoolExecutor(3) as ex:
        for k, o in enumerate(ex.map(render_beat, todo)):
            if k % 10 == 0:
                print("rendered", k + 1, "/", len(todo), flush=True)


# ---------------------------------------------------------------- subtitles
def split_chunks(text, maxlen=58):
    parts = re.split(r"(?<=[,.:;?!])\s+", text.strip())
    chunks = []
    cur = ""
    for p in parts:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= maxlen:
            cur += " " + p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    # hard-split very long chunks on spaces
    res = []
    for c in chunks:
        while len(c) > maxlen + 12:
            cut = c.rfind(" ", 0, maxlen)
            res.append(c[:cut])
            c = c[cut + 1:]
        res.append(c)
    return res


def wrap2(c, maxline=30):
    if len(c) <= maxline:
        return c
    words = c.split()
    best, bi = 1e9, 1
    for i in range(1, len(words)):
        l1 = len(" ".join(words[:i])); l2 = len(" ".join(words[i:]))
        if max(l1, l2) < best:
            best, bi = max(l1, l2), i
    return " ".join(words[:bi]) + "\\N" + " ".join(words[bi:])


def ass_time(t):
    t = max(t, 0)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(plan, path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Roboto,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,5,2,5,40,40,0,1
Style: Title,Roboto,58,&H0000E5FF,&H00FFFFFF,&H00000000,&HA0000000,1,0,0,0,100,100,1,0,3,14,0,8,30,30,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    t0 = 0.0
    hook_end = 0.0
    for p in plan:
        chunks = split_chunks(p["text"])
        weights = [max(len(c.split()), 1) + 0.6 * len(re.findall(r"[,.:;?!]", c)) for c in chunks]
        tot = sum(weights)
        t = t0
        for c, w_ in zip(chunks, weights):
            d = p["audio_dur"] * w_ / tot
            ev.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},Sub,,0,0,0,,{{\\an5\\pos({W // 2},{BAND_Y + BAND_H // 2})}}{wrap2(c)}")
            t += d
        if p["i"] < 5:
            hook_end = t0 + p["dur"]
        t0 += p["dur"]
    ev.insert(0, f"Dialogue: 1,{ass_time(0)},{ass_time(hook_end)},Title,,0,0,0,,{{\\fad(400,400)}}{wrap2(TITLE, 26)}")
    open(path, "w", encoding="utf-8-sig").write(head + "\n".join(ev) + "\n")
    return t0


# ---------------------------------------------------------------- final
def stage_final(plan, name="review_vi.mp4"):
    # 1) concat beat videos
    lst = os.path.join(WORK, "beats_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in plan:
            bp = os.path.join(SEG, "%03d.mp4" % (p["i"] + 1)).replace("\\", "/")
            f.write(f"file '{bp}'\n")
    joined = os.path.join(WORK, "joined.mp4")
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    # 2) narration track, each beat padded/trimmed to exact beat length (sample accurate, pure python)
    nar = os.path.join(WORK, "narration_full.wav")
    with wave.open(nar, "wb") as wo:
        wo.setnchannels(1); wo.setsampwidth(2); wo.setframerate(48000)
        t_samples = 0
        t_exact = 0.0
        for p in plan:
            with wave.open(p["wav"]) as wi:
                assert wi.getframerate() == 48000 and wi.getnchannels() == 1 and wi.getsampwidth() == 2
                data = wi.readframes(wi.getnframes())
            t_exact += p["dur"]
            need = round(t_exact * 48000) - t_samples
            data = data[:need * 2] + b"\x00\x00" * max(0, need - len(data) // 2)
            wo.writeframes(data)
            t_samples += need
    # 3) subtitles
    ass = os.path.join(WORK, "subs_vi.ass")
    total = build_ass(plan, ass)
    ass_ff = ass.replace("\\", "/").replace(":", "\\:")
    fonts_ff = "C\\:/Windows/Fonts"
    out = os.path.join(OUT, name)
    vf = f"subtitles='{ass_ff}':fontsdir='{fonts_ff}',fade=t=in:st=0:d=0.5,fade=t=out:st={total - 1.2:.2f}:d=1.2"
    af = (f"[1:a]aformat=channel_layouts=stereo,volume=1.0,acompressor=threshold=-18dB:ratio=3:attack=5:release=120[n];"
          f"[0:a]volume=1.0[o];[n][o]amix=inputs=2:duration=first:normalize=0,"
          f"loudnorm=I=-15:TP=-1.5:LRA=11,afade=t=out:st={total - 1.2:.2f}:d=1.2[a]")
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", joined, "-i", nar, "-vf", vf,
         "-filter_complex", af, "-map", "0:v", "-map", "[a]",
         "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "20", "-b:v", "0", "-maxrate", "16M", "-bufsize", "32M",
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", out])
    print(f"FINAL: {out}  ({total / 60:.2f} min)")
    return out


if __name__ == "__main__":
    stages = sys.argv[1:] or ["audio", "plan", "beats", "final"]
    info = stage_audio() if "audio" in stages else json.load(open(os.path.join(WORK, "beats_audio.json")))
    plan = stage_plan(info) if "plan" in stages else json.load(open(os.path.join(WORK, "plan.json"), encoding="utf-8"))
    if "beats" in stages:
        stage_beats(plan)
    if "final" in stages:
        stage_final(plan)

