"""Input box, list picker and text prompt."""
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static, TextArea


class Prompt(TextArea):  # multi-line input: enter sends, ctrl+j newline; drives the / menu
    BINDINGS = [Binding("enter", "send", "send", priority=True), Binding("ctrl+j", "newline", "newline", priority=True),
                Binding("up", "menu(-1)", show=False, priority=True), Binding("down", "menu(1)", show=False, priority=True),
                Binding("tab", "complete", show=False, priority=True), Binding("escape", "close_menu", show=False, priority=True)]
    class Submitted(Message):
        def __init__(s, value): super().__init__(); s.value = value
    def menu_open(s): return s.app.query_one("#slash").display
    def check_action(s, action, params):  # menu keys only act while the menu is open
        return s.menu_open() if action in ("menu", "complete", "close_menu") else True
    def action_send(s):
        if s.menu_open(): return s.app.slash_choose()
        s.post_message(s.Submitted(s.text)); s.clear()
    def action_newline(s): s.insert("\n")
    def action_menu(s, d): s.app.slash_move(d)
    def action_complete(s): s.app.slash_choose(complete_only=True)
    def action_close_menu(s): s.app.query_one("#slash").display = False


class Picker(ModalScreen):
    CSS = "Picker { align: center middle; } OptionList { width: 90%; max-height: 80%; border: round $accent; }"
    BINDINGS = [("escape", "dismiss(None)", "close")]
    def __init__(s, title, items): super().__init__(); s.title_, s.items = title, items
    def compose(s):
        ol = OptionList(*[i[0] for i in s.items] or ["(nothing found)"]); ol.border_title = s.title_; yield ol
    def on_option_list_option_selected(s, e):
        s.dismiss(s.items[e.option_index][1] if s.items else None)

class Ask(ModalScreen):
    CSS = "Ask { align: center middle; } #box { width: 80%; height: auto; border: round $accent; padding: 0 1; }"
    BINDINGS = [("escape", "dismiss(None)", "close")]
    def __init__(s, title, hint): super().__init__(); s.title_, s.hint = title, hint
    def compose(s):
        with Vertical(id="box"):
            yield Static(s.title_); yield Input(placeholder=s.hint)
    def on_input_submitted(s, e): e.stop(); s.dismiss(e.value.strip() or None)
