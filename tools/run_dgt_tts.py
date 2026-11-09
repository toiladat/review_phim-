# -*- coding: utf-8 -*-
"""
Automated DGT Auto TTS runner via local MCP server (http://localhost:39217/mcp).
- Automatically launches DgtAutoTTSMM.exe and logs in if port 39217 is not active.
- Ensures the locked-in voice sample (tools/voice_sample_v2.mp3) is cloned & selected.
- Enforces model="speech-02-hd", speed=1.0, change_speed=False.
- Loads work/tts/narration.srt and runs start_tts until all lines are 100% downloaded,
  automatically resuming if any lines hit Retry: 25 due to server 429/503.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = "http://localhost:39217/mcp"
DGT_DIR = r"C:\Users\Admin\Downloads\DgtAutoTTSMM_v5\DgtAutoTTSMM_v5"
DGT_EXE = os.path.join(DGT_DIR, "DgtAutoTTSMM.exe")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_SAMPLE = os.path.join(ROOT_DIR, "tools", "voice_sample_v2.mp3")
DEFAULT_SRT = os.path.join(ROOT_DIR, "work", "tts", "narration.srt")

sid = None
_req_id = 0


def mcp_rpc(method, params=None, notify=False, timeout=120):
    global sid, _req_id
    _req_id += 1
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if not notify:
        body["id"] = _req_id
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-03-26",
    }
    if sid:
        headers["Mcp-Session-Id"] = sid
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        sid = r.headers.get("Mcp-Session-Id") or sid
        raw = r.read().decode("utf-8", "replace")
        ctype = r.headers.get("Content-Type", "")
    if notify or not raw.strip():
        return None
    if "event-stream" in ctype:
        datas = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
        return json.loads(datas[-1]) if datas else None
    return json.loads(raw)


def mcp_tool(name, args=None, timeout=120):
    r = mcp_rpc("tools/call", {"name": name, "arguments": args or {}}, timeout=timeout)
    res = r.get("result", r)
    out = []
    for c in res.get("content", []):
        out.append(c.get("text", json.dumps(c, ensure_ascii=False)))
    text = "\n".join(out) or json.dumps(res, ensure_ascii=False)
    try:
        return json.loads(text)
    except Exception:
        return text


def ensure_dgt_running():
    global sid
    sid = None
    try:
        mcp_rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "review-tool-tts", "version": "1.0"},
            },
            timeout=3,
        )
        mcp_rpc("notifications/initialized", notify=True, timeout=3)
        print("[DGT] Connected to existing MCP server on port 39217.")
        return None
    except Exception:
        pass

    print(f"[DGT] Starting {DGT_EXE} ...")
    env = os.environ.copy()
    env["__COMPAT_LAYER"] = "RunAsInvoker"
    proc = subprocess.Popen([DGT_EXE], cwd=DGT_DIR, env=env)
    time.sleep(3)

    from pywinauto.application import Application

    app = Application(backend="win32").connect(process=proc.pid)
    w = app.window(title="Login")
    for c in w.children():
        if c.window_text() == "Login":
            c.click()
            print("[DGT] Clicked Login button.")
            break

    for _ in range(15):
        time.sleep(1)
        try:
            sid = None
            mcp_rpc(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "review-tool-tts", "version": "1.0"},
                },
                timeout=3,
            )
            mcp_rpc("notifications/initialized", notify=True, timeout=3)
            print("[DGT] MCP server ready on port 39217.")
            return proc
        except Exception:
            pass
    raise RuntimeError("Failed to connect to DGT MCP server after launching DgtAutoTTSMM.exe")


def main():
    srt_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRT
    srt_path = os.path.abspath(srt_path)
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    proc = ensure_dgt_running()

    voices = mcp_tool("list_voices")
    print("[DGT] list_voices:", json.dumps(voices, ensure_ascii=False))
    target_voice = None
    if isinstance(voices, list):
        for v in voices:
            vname = v.get("voice_name", "")
            if vname.startswith("viet_rv_v2"):
                target_voice = vname
                break

    if not target_voice:
        print(f"[DGT] Cloning voice from {VOICE_SAMPLE} ...")
        res = mcp_tool(
            "clone_voice",
            {
                "voice_name": "viet_rv_v2",
                "language": "Vietnamese",
                "sample_path": VOICE_SAMPLE,
                "agree_terms": True,
                "select": True,
            },
            timeout=120,
        )
        print("[DGT] clone_voice:", json.dumps(res, ensure_ascii=False))
        target_voice = res.get("voice_name") if isinstance(res, dict) else "viet_rv_v2"
    else:
        res = mcp_tool("select_voice", {"voice_name": target_voice})
        print("[DGT] select_voice:", json.dumps(res, ensure_ascii=False))

    settings_res = mcp_tool(
        "set_tts_settings",
        {"model": "speech-02-hd", "speed": 1.0, "change_speed": False},
    )
    print("[DGT] set_tts_settings:", json.dumps(settings_res, ensure_ascii=False))

    load_res = mcp_tool("load_input", {"file_path": srt_path})
    print("[DGT] load_input:", json.dumps(load_res, ensure_ascii=False))

    pass_num = 0
    while True:
        st = mcp_tool("get_status")
        total = st.get("total_lines", 0)
        done = st.get("done", 0)
        running = st.get("is_running", False)
        proc_cnt = st.get("processing", 0)
        print(
            f"[DGT] Status: done={done}/{total}, processing={proc_cnt}, "
            f"is_running={running}, voice={st.get('selected_voice')}, "
            f"voice_id={st.get('voice_id')}, speed={st.get('speed')}"
        )
        if total > 0 and done >= total:
            print(f"[DGT] All {done}/{total} lines completed successfully!")
            break
        if not running:
            pass_num += 1
            print(f"[DGT] Starting TTS pass #{pass_num} ...")
            start_res = mcp_tool(
                "start_tts",
                {"allow_long_lines": True, "merge_short_lines": False},
            )
            print("[DGT] start_tts:", json.dumps(start_res, ensure_ascii=False))
        time.sleep(10)


if __name__ == "__main__":
    main()

