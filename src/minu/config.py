"""Paths, limits, prompts and the banner."""
import os, platform, re
from pathlib import Path

HOME = Path.home()
HF = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", HOME / ".cache/huggingface")) / "hub")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA = OLLAMA if OLLAMA.startswith("http") else "http://" + OLLAMA
CTX = int(os.environ.get("MINU_CTX", 16384))
DIR = HOME / ".cache/minu"
MINU_HOME = Path(os.environ.get("MINU_HOME") or HOME / ".minu").expanduser()  # sessions live here
OUT_MAX, STEPS = 4000, 25
MLX_OK = platform.system() == "Darwin" and platform.machine() == "arm64"
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
IMG_RE = re.compile(r"[\w~./-]+\.(?:png|jpe?g|gif|webp|bmp)\b", re.I)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
OS = {"Darwin": "macOS"}.get(platform.system(), platform.system())
ENV = f"on {OS}, cwd {os.getcwd()}"
SYSTEM = (f"You are minu, a terse coding agent {ENV}. You can run shell commands and use the web. "
          "To run one, reply with only a ```sh block, then stop; you get its output. Example:\n"
          "```sh\nminu-search \"turing machine\"\n```\n"
          "minu-fetch URL reads a page. Edit files with heredoc or python3. Use ```text for examples.")
SYSTEM_NATIVE = (f"You are minu, a terse coding agent {ENV}. Use the sh tool to run commands and use the web: "
                 "minu-search \"query\", minu-fetch URL. Edit files with heredoc or python3.")
COMMANDS = [  # shown in the / menu: (command, argument, description)
    ("/new", "", "start a new session"),
    ("/model", "", "pick or download a model"),
    ("/delete", "", "delete a downloaded model to free disk space"),
    ("/resume", "", "open a saved session"),
    ("/search", "<query>", "search the web, the model answers from the results"),
    ("/fetch", "<url>", "read a web page, the model summarizes it"),
    ("/view", "<image>", "show an image"),
    ("/auto", "", "toggle running commands without asking"),
    ("/clear", "", "same as /new"),
    ("/exit", "", "quit minu"),
]
TOOLS = [{"type": "function", "function": {"name": "sh", "description": "Run a shell command",
          "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]
BLOCK = re.compile(r"```(?:sh|bash|shell|zsh)[ \t]*\n(.*?)```|<tool_call>(.*?)</tool_call>", re.S)
BANNER = """\
███╗   ███╗ ██╗ ███╗   ██╗ ██╗   ██╗
████╗ ████║ ██║ ████╗  ██║ ██║   ██║
██╔████╔██║ ██║ ██╔██╗ ██║ ██║   ██║
██║╚██╔╝██║ ██║ ██║╚██╗██║ ██║   ██║
██║ ╚═╝ ██║ ██║ ██║ ╚████║ ╚██████╔╝
╚═╝     ╚═╝ ╚═╝ ╚═╝  ╚═══╝  ╚═════╝

[dim]tiny harness for local models
ctrl+o  pick or download a model  ·  drop an image path to attach it[/]"""
