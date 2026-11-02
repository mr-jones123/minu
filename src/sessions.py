"""Sessions saved as .minu/sessions/<timestamp>.jsonl, one message per line."""
import asyncio, json, os, time
from pathlib import Path

from textual import work
from textual.widgets import Markdown, Static

from .widgets import Picker

SESS = Path.cwd() / ".minu" / "sessions"

def sessions():  # newest first: (label, path)
    out = []
    for p in sorted(SESS.glob("*.jsonl"), reverse=True)[:50]:
        first, n = "", 0
        for line in p.read_text(errors="replace").splitlines():
            m = json.loads(line)
            if m.get("role") == "user" and not first:
                c = m["content"] if isinstance(m["content"], str) else m["content"][0]["text"]
                first = c.replace("\n", " ")[:60]
            n += "role" in m
        out.append((f"{p.stem.replace('_', ' ')}  ({n} msgs)  {first}", p))
    return out


class SessionsMixin:
    def push(s, m):
        s.msgs.append(m)
        if not s.session:
            SESS.mkdir(parents=True, exist_ok=True)
            (SESS.parent / ".gitignore").write_text("*\n")
            s.session = SESS / (time.strftime("%Y-%m-%d_%H-%M-%S") + ".jsonl")
            with open(s.session, "a") as f: f.write(json.dumps({"meta": {"cwd": os.getcwd(), "model": s.srv.name}}) + "\n")
        with open(s.session, "a") as f: f.write(json.dumps(m) + "\n")

    def resume(s, path):
        s.action_clear()
        msgs = [m for m in map(json.loads, Path(path).read_text().splitlines()) if "role" in m]
        s.msgs, s.session = s.msgs[:1] + [m for m in msgs if m["role"] != "system"], Path(path)
        for m in s.msgs[1:]:
            c = m.get("content") or ""
            if m["role"] == "user" and isinstance(c, str) and c.startswith("Output:\n") or m["role"] == "tool":
                lines = (c.removeprefix("Output:\n")).splitlines()
                s.note("\n".join(lines[:15]) + (f"\n… ({len(lines) - 15} more lines)" if len(lines) > 15 else ""), "out")
            elif m["role"] == "user":
                txt = c if isinstance(c, str) else c[0]["text"] + f"  [{len(c) - 1} image(s)]"
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
        if p := await s.push_screen_wait(Picker("sessions in .minu/", items)): s.resume(p)
