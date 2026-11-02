"""The agent loop: stream a reply, run its command, feed the output back."""
import json, re, time

from textual import work
from textual.widgets import Markdown

from .config import BLOCK, STEPS
from .images import mentioned_images
from .tools import fetch, search, sh, strip_think, to_cmd


class AgentMixin:
    def approve(s, cmd):
        if s.auto: s.ui(s.note, f"$ {cmd}", "cmd"); return True
        s.ui(s.note, f"$ {cmd}", "cmd")
        return s.ask("run it?")

    def exec_cmd(s, cmd):
        if not s.approve(cmd): return "[user declined to run this]"
        s.set_state("running…")
        out = sh(cmd); s.state = ""
        lines = out.splitlines()
        s.ui(s.note, "\n".join(lines[:15]) + (f"\n… ({len(lines) - 15} more lines)" if len(lines) > 15 else ""), "out")
        return out

    def web(s, kind, arg):  # /search and /fetch: look it up, show it, hand it to the model
        s.set_state(f"{'searching' if kind == 'search' else 'fetching'}…")
        try: res = search(arg) if kind == "search" else fetch(arg)
        except Exception as e: res = f"{kind} failed: {e}"
        lines = res.splitlines()
        s.ui(s.note, "\n".join(lines[:20]) + (f"\n… ({len(lines) - 20} more lines)" if len(lines) > 20 else ""), "out")
        if not s.srv.url: return s.say("▸ no model loaded, so just showing results (ctrl+o to pick one)")
        ask = (f'Web search results for "{arg}":\n\n{res}\n\nAnswer "{arg}" now from these results, citing URLs. Do not run any commands.' if kind == "search"
               else f"Contents of {arg}:\n\n{res}\n\nSummarize this page.")
        s.push({"role": "user", "content": ask}); return True

    @work(thread=True, exclusive=True, group="turn")
    def turn(s, pre=None):
        s.busy = True; s.stop_ev.clear()
        try:
            if not pre or s.web(*pre):  # web() returns None when there's no model to answer
                for _ in range(STEPS):
                    if s.step(): break
        except Exception as e:
            msg = str(e)
            if re.search(r"image|mmproj|multimodal|vision", msg, re.I) and any(isinstance(m["content"], list) for m in s.msgs):
                for m in s.msgs:  # drop images so the chat can continue
                    if isinstance(m["content"], list):
                        m["content"] = m["content"][0]["text"] + "\n[image removed: model can't see images]"
                msg = "this model can't read images. Pick one marked [vision] (ctrl+o), or e.g. gemma3:4b on Ollama"
            s.say(f"▸ error: {msg}")
        s.busy = False; s.set_state("")

    def step(s):
        md = s.ui(s.add, Markdown(""))
        raw, calls, last, block = "", {}, 0.0, None
        s.set_state("thinking…")
        for ch in s.srv.stream(s.msgs, s.native, s.stop_ev):
            if u := ch.get("usage"): s.used = u.get("total_tokens") or u.get("prompt_tokens", 0) + u.get("completion_tokens", 0)
            if not ch.get("choices"): continue
            d = ch["choices"][0].get("delta") or {}
            raw += d.get("content") or ""
            for tc in d.get("tool_calls") or []:
                c = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                f = tc.get("function") or {}
                c["id"] = tc.get("id") or c["id"]; c["name"] += f.get("name") or ""; c["args"] += f.get("arguments") or ""
            text = strip_think(raw)
            if not s.native and (block := BLOCK.search(text)):
                break
            if time.time() - last > 0.1 and text:
                s.ui(md.update, text); s.set_state("writing…"); last = time.time()
        text = strip_think(raw)
        if block: text = text[:block.end()]
        s.ui(md.update, text or ("" if calls else "_(empty)_"))
        if s.stop_ev.is_set():
            s.push({"role": "assistant", "content": text}); s.say("▸ stopped"); return True
        if calls:
            s.push({"role": "assistant", "content": text, "tool_calls": [
                {"id": c["id"] or f"call{i}", "type": "function", "function": {"name": c["name"], "arguments": c["args"]}}
                for i, c in calls.items()]})
            for i, c in calls.items():
                try: cmd = json.loads(c["args"] or "{}").get("command", "")
                except json.JSONDecodeError: cmd = c["args"]
                s.push({"role": "tool", "tool_call_id": c["id"] or f"call{i}", "content": s.exec_cmd(cmd)})
            return s.stop_ev.is_set()
        s.push({"role": "assistant", "content": text})
        if block:
            s.push({"role": "user", "content": "Output:\n" + s.exec_cmd(to_cmd(block))})
            return s.stop_ev.is_set()
        for p in mentioned_images(text): s.ui(s.show_image, p)
        return True
