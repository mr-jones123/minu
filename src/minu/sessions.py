"""Sessions saved as ~/.minu/sessions/<project>/<timestamp>.jsonl: a meta line, then one message per line."""
import asyncio, json, re, threading, time
from pathlib import Path

from textual import work
from textual.widgets import Markdown, Static

from .config import MINU_HOME
from .widgets import Picker

ROOT = MINU_HOME / "sessions"
CWD = Path.cwd().resolve()
SESS = ROOT / re.sub(r"[^\w.-]", "-", str(CWD))  # one folder per project, e.g. -Users-me-code-app
LEGACY = CWD / ".minu" / "sessions"              # where older versions saved, still listed
_lock = threading.Lock()

def read_jsonl(p):
    out = []
    for line in Path(p).read_text(errors="replace").splitlines():
        try: out.append(json.loads(line))
        except json.JSONDecodeError: pass  # half-written line from a crash
    return out

def session_files():  # this project's sessions, newest first
    files = [*SESS.glob("*.jsonl"), *(LEGACY.glob("*.jsonl") if LEGACY.is_dir() else [])]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

def text_of(c): return c if isinstance(c, str) else next((x.get("text", "") for x in c if x.get("type") == "text"), "")

def sessions():  # (label, path) for the picker
    out = []
    for p in session_files()[:50]:
        msgs = [m for m in read_jsonl(p) if "role" in m]
        first = next((text_of(m["content"]) for m in msgs if m["role"] == "user"), "").replace("\n", " ")[:60]
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
        out.append((f"{when}  ({len(msgs)} msgs)  {first}", p))
    return out


class SessionsMixin:
    def push(s, m):
        s.msgs.append(m)
        with _lock:  # called from the UI and worker threads
            if not s.session:
                SESS.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y-%m-%d_%H-%M-%S"); p, i = SESS / f"{stamp}.jsonl", 1
                while p.exists(): p, i = SESS / f"{stamp}-{i}.jsonl", i + 1
                s.session = p
                meta = {"cwd": str(CWD), "model": s.srv.name, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
                with open(p, "a") as f: f.write(json.dumps({"meta": meta}) + "\n")
            with open(s.session, "a") as f: f.write(json.dumps(m) + "\n")

    def resume(s, path):
        s.action_clear()
        msgs = [m for m in read_jsonl(path) if "role" in m]
        s.msgs, s.session = s.msgs[:1] + [m for m in msgs if m["role"] != "system"], Path(path)
        for m in s.msgs[1:]:
            c = m.get("content") or ""
            if m["role"] == "user" and isinstance(c, str) and c.startswith("Output:\n") or m["role"] == "tool":
                lines = (c.removeprefix("Output:\n")).splitlines()
                s.note("\n".join(lines[:15]) + (f"\n… ({len(lines) - 15} more lines)" if len(lines) > 15 else ""), "out")
            elif m["role"] == "user":
                txt = c if isinstance(c, str) else text_of(c) + f"  [{len(c) - 1} image(s)]"
                s.add(Static(f"> {txt}", classes="user", markup=False))
            elif m["role"] == "assistant":
                if c: s.add(Markdown(c))
                for t in m.get("tool_calls") or []:
                    try: s.note("$ " + json.loads(t["function"]["arguments"]).get("command", ""), "cmd")
                    except Exception: pass
        s.note(f"▸ resumed {Path(path).name} ({len(msgs)} messages)")

    @work(exclusive=True, group="pick")
    async def pick_session(s):
        items = await asyncio.to_thread(sessions)
        if p := await s.push_screen_wait(Picker(f"sessions for {CWD.name}", items)): s.resume(p)
