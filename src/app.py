"""The minu TUI: layout, status bar, input handling."""
import os, subprocess, threading, time, re

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, OptionList, Static

from .agent import AgentMixin
from .config import BANNER, COMMANDS, SYSTEM, SYSTEM_NATIVE
from .images import encode_image, find_images, image_widget
from .model_flows import ModelFlowsMixin
from .server import Server, kill_children
from .sessions import SessionsMixin
from .tools import sh_env
from .widgets import Prompt


class Minu(ModelFlowsMixin, SessionsMixin, AgentMixin, App):
    CSS = """
    #banner { height: 1fr; width: 100%; content-align: center middle; text-align: center; color: $accent; }
    #log { height: 1fr; padding: 0 1; scrollbar-size-vertical: 1; display: none; }
    .user { color: $accent; margin-top: 1; text-style: bold; }
    .cmd { color: $warning; }
    .out { color: $text-muted; }
    .sys { color: $text-muted; text-style: italic; }
    .img { width: auto; height: 14; margin: 0 2; }
    Markdown { margin: 0; padding: 0; }
    .think-box { background: transparent; border: none; padding: 0; margin: 1 0 0 0; }
    .think-box > Contents { padding: 0 0 0 2; }
    .think-box CollapsibleTitle { color: $text-muted; padding: 0; }
    .think { color: $text-muted; text-style: italic; }
    #prompt { height: auto; min-height: 5; max-height: 12; border: round $accent; padding: 0 1; background: $surface; }
    #prompt:focus { border: round $accent-lighten-2; }
    #prompt > .text-area--cursor-line { background: transparent; }
    #status { height: 1; padding: 0 1; color: $text-muted; background: $panel; }
    #slash { height: auto; max-height: 11; border: round $accent; background: $surface; display: none; padding: 0 1; }
    """
    BINDINGS = [("ctrl+o", "pick", "model"), ("ctrl+y", "auto", "auto-run"),
                ("escape", "halt", "stop"), ("ctrl+l", "clear", "clear"), ("ctrl+n", "clear", "new session"),
                Binding("ctrl+c", "quit", "quit", show=False, priority=True)]  # beats TextArea's ctrl+c copy

    def __init__(s, start=None, auto=False, native=False, resume=None):
        super().__init__()
        s.resume_path = resume
        s.srv, s.start_with, s.auto, s.native = Server(), start, auto, native
        s.msgs = [{"role": "system", "content": SYSTEM_NATIVE if native else SYSTEM}]
        s.used, s.busy, s.state, s.ollama_proc, s.session, s.tps = 0, False, "", None, None, None
        s.stop_ev, s.ok_ev, s.ok, s.pending = threading.Event(), threading.Event(), False, False

    def compose(s) -> ComposeResult:
        yield Static(BANNER, id="banner")
        yield VerticalScroll(id="log")
        yield OptionList(id="slash")
        p = Prompt(id="prompt", placeholder="ask minu…  (type / for commands)", soft_wrap=True)
        p.border_title, p.border_subtitle = "message", "enter send · ctrl+j newline"
        yield p
        yield Static(id="status")

    def on_mount(s):
        s.title = "minu"; s.status(); s.query_one("#prompt").focus()
        if s.resume_path: s.resume(s.resume_path)
        if s.start_with: s.load(*s.start_with)
        else: s.action_pick()

    def on_click(s, e):  # click anywhere on the chat -> type in the input box
        if len(s.screen_stack) == 1: s.query_one("#prompt").focus()

    def on_unmount(s):
        s.srv.stop()
        if s.ollama_proc: s.ollama_proc.terminate()

    # ---- ui helpers (main thread)
    def status(s):
        ctx = f"{s.used}/{s.srv.ctx}" if s.srv.ctx else str(s.used)
        st = f" · {s.state}" if s.state else ""
        tps = f" · {s.tps:.1f} tok/s" if s.tps else ""
        s.query_one("#status", Static).update(
            f"{s.srv.name} · {ctx} tok{tps} · auto {'on' if s.auto else 'off'}{st}   ^o model ^y auto esc stop ^c quit")

    def add(s, w):
        s.query_one("#banner").display = False
        log = s.query_one("#log"); log.display = True
        log.mount(w); s.call_after_refresh(log.scroll_end, animate=False); return w

    async def render(s, w, text):  # update a streaming widget; follow the bottom unless the user scrolled up
        log = s.query_one("#log"); pinned = log.max_scroll_y - log.scroll_y <= 3
        if (r := w.update(text)) is not None: await r
        if pinned: s.call_after_refresh(log.scroll_end, animate=False)

    def add_think(s):  # live reasoning, shown in the chat and folded away once the answer starts
        body = Static("", classes="think", markup=False)
        box = s.add(Collapsible(body, title="thinking…", collapsed=False, classes="think-box"))
        return box, body

    def end_think(s, box, secs): box.title, box.collapsed = f"thought for {secs:.1f}s", True

    def note(s, text, cls="sys"): return s.add(Static(text, classes=cls, markup=False))

    def show_image(s, p):
        try: s.add(image_widget(p))
        except Exception as e: s.note(f"▸ can't show {p.name}: {e}")

    def ui(s, fn, *a):  # call from worker thread
        return s.call_from_thread(fn, *a)

    def say(s, text): s.ui(s.note, text)
    def set_state(s, text): s.state = text; s.ui(s.status)

    # ---- actions
    def action_quit(s):  # unblock worker threads first, or the app hangs on exit waiting for them
        s.stop_ev.set(); s.ok, s.pending = False, False; s.ok_ev.set(); s.srv.abort()
        t = threading.Timer(4, lambda: (kill_children(), os._exit(0))); t.daemon = True  # last resort if a thread is still stuck
        t.start()
        s.exit()

    def action_auto(s): s.auto = not s.auto; s.status()
    def action_halt(s):
        s.stop_ev.set()
        if s.pending: s.ok = False; s.pending = False; s.ok_ev.set()

    def action_clear(s):
        if s.busy: return s.notify("busy, press esc first")
        s.msgs = s.msgs[:1]; s.used = 0; s.session = None; s.tps = None
        log = s.query_one("#log"); log.remove_children(); log.display = False
        s.query_one("#banner").display = True; s.status()

    # ---- worker-thread helpers
    def ask(s, q):
        s.say(q)
        def go():
            s.pending = True; inp = s.query_one("#prompt"); inp.placeholder = "[Y/n]  enter = yes"; inp.focus()
        s.ok_ev.clear(); s.ui(go); s.ok_ev.wait()
        return s.ok

    def proc(s, cmd, label):  # run a long command, live last line in the status bar
        p = subprocess.Popen(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, env={**sh_env(), "PYTHONUNBUFFERED": "1"})
        tail, buf, last = [], b"", 0.0
        while chunk := p.stdout.read1(4096):
            buf += chunk
            *lines, buf = re.split(rb"[\r\n]", buf)
            tail = (tail + [x.decode(errors="replace").strip() for x in lines if x.strip()])[-20:]
            if time.time() - last > 0.2:
                cur = buf.decode(errors="replace").strip() or (tail[-1] if tail else "")
                s.set_state(f"{label}: {cur[-70:]}"); last = time.time()
            if s.stop_ev.is_set(): p.terminate()
        if buf.strip(): tail.append(buf.decode(errors="replace").strip())
        s.set_state("")
        return p.wait(), tail

    # ---- the / menu
    def on_text_area_changed(s, e):
        if e.text_area.id != "prompt": return
        t, menu = e.text_area.text, s.query_one("#slash", OptionList)
        s.menu_items = [c for c in COMMANDS if c[0].startswith(t)] if t.startswith("/") and not re.search(r"\s", t) else []
        if s.menu_items:
            menu.set_options([f"{c:<9}{a:<10}{d}" for c, a, d in s.menu_items]); menu.highlighted = 0
        menu.display = bool(s.menu_items)

    def slash_move(s, d):
        menu = s.query_one("#slash", OptionList)
        menu.highlighted = ((menu.highlighted or 0) + d) % len(s.menu_items)

    def slash_choose(s, complete_only=False, index=None):
        menu, inp = s.query_one("#slash", OptionList), s.query_one("#prompt")
        cmd, arg, _ = s.menu_items[menu.highlighted if index is None else index]
        menu.display = False
        if arg or complete_only:  # needs an argument: fill it in and keep typing
            inp.text = cmd + " "; inp.move_cursor(inp.document.end); inp.focus()
        else:
            inp.clear(); s.on_prompt_submitted(Prompt.Submitted(cmd))

    def on_option_list_option_selected(s, e):
        if e.option_list.id == "slash": s.slash_choose(index=e.option_index)

    def on_prompt_submitted(s, e):
        text = e.value.strip(); inp = s.query_one("#prompt")
        if s.pending:
            s.ok = text.lower() in ("", "y", "yes"); s.pending = False
            inp.placeholder = "ask minu…"; s.ok_ev.set(); return
        if not text: return
        if text == "/model": return s.action_pick()
        if text in ("/new", "/clear"): return s.action_clear()
        if text == "/auto": return s.action_auto()
        if text == "/resume": return s.pick_session()
        if text in ("/exit", "/quit", "/q"): return s.action_quit()
        if text.startswith("/view"):
            imgs = find_images(text[5:])
            return [s.show_image(p) for p in imgs] if imgs else s.notify("no image file at that path")
        if s.busy: return s.notify("busy, esc to stop")
        if m := re.match(r"/(search|fetch)\s+(.+)", text, re.S):
            s.add(Static(f"> {text}", classes="user", markup=False)); return s.turn((m[1], m[2].strip()))
        if re.fullmatch(r"/[a-z]+", text.split()[0]) and not Path(text.split()[0]).exists():  # not a pasted path
            return s.notify(f"unknown command {text.split()[0]} (type / to see them)")
        if not s.srv.url: return s.notify("no model loaded (ctrl+o)")
        imgs = find_images(text)
        s.add(Static(f"> {text}", classes="user", markup=False))
        for p in imgs: s.show_image(p)
        content = text
        if imgs:
            try: content = [{"type": "text", "text": text}] + [{"type": "image_url", "image_url": {"url": encode_image(p)}} for p in imgs]
            except Exception as err: s.note(f"▸ couldn't read image: {err}")
        s.push({"role": "user", "content": content}); s.turn()
