"""Command line: `minu [--hf|--gguf|--mlx|--ollama|--url ...]`, plus `minu search|fetch` for the agent."""
import argparse, os, signal, sys

from . import images
from .sessions import SESS
from .tools import fetch, search, shims


def main():
    if len(sys.argv) > 2 and sys.argv[1] in ("search", "fetch"):
        try: print((search if sys.argv[1] == "search" else fetch)(" ".join(sys.argv[2:])))
        except Exception as e: print(f"error: {e}"); sys.exit(1)
        return
    ap = argparse.ArgumentParser(prog="minu", description="tiny agent harness for local models")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hf", help="HF repo; GGUF -> llama.cpp, mlx -> MLX")
    g.add_argument("--gguf", help="HF GGUF repo or .gguf path (llama.cpp)")
    g.add_argument("--mlx", help="HF MLX repo (mlx_lm)")
    g.add_argument("--ollama", help="Ollama model name")
    g.add_argument("--url", help="existing OpenAI-compatible server")
    ap.add_argument("-y", "--auto", action="store_true", help="run commands without asking")
    ap.add_argument("--native", action="store_true", help="use native tool calls instead of ```sh blocks")
    ap.add_argument("-c", "--continue", dest="cont", action="store_true", help="continue the latest session in .minu/")
    ap.add_argument("-r", "--resume", metavar="FILE", help="resume a session .jsonl")
    a = ap.parse_args()
    start = None
    if a.hf:
        low = a.hf.lower()
        if "gguf" in low: start = ("gguf", a.hf)
        elif "mlx" in low: start = ("mlx", a.hf)
        else: ap.error("can't tell if repo is GGUF or MLX; use --gguf or --mlx")
    for k in ("gguf", "mlx", "ollama", "url"):
        if getattr(a, k): start = (k, getattr(a, k))
    shims()
    import logging; logging.getLogger("textual_image").setLevel(logging.CRITICAL)
    try: import textual_image.widget  # noqa: F401  (must detect terminal graphics before the app starts)
    except Exception: images.IMAGES = False  # odd terminal: show image names instead of pixels
    resume = a.resume
    if a.cont:
        latest = sorted(SESS.glob("*.jsonl"))
        resume = latest[-1] if latest else None
        if not resume: print("no sessions in .minu/ yet")
    from .app import Minu  # imported late so `minu search|fetch` stay fast
    from .server import kill_children
    app = Minu(start, a.auto, a.native, resume)
    signal.signal(signal.SIGTERM, lambda *_: app.exit())
    signal.signal(signal.SIGHUP, lambda *_: (kill_children(), os._exit(1)))  # terminal closed
    app.run()
