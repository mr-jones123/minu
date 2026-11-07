"""Starting/stopping model servers and streaming chat completions."""
import atexit, importlib.util, json, socket, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

from .config import CTX, DIR, OLLAMA, TOOLS
from .installs import which
from .tools import get

CHILDREN = []  # every server minu starts, so they never outlive it

def spawn(cmd, **kw):
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **kw); CHILDREN.append(p); return p

@atexit.register
def kill_children():
    for p in CHILDREN:
        if p.poll() is None: p.terminate()
    for p in CHILDREN:
        try: p.wait(3)
        except subprocess.TimeoutExpired: p.kill()

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

class Server:
    def __init__(s): s.proc, s.url, s.model, s.name, s.kind, s.ctx, s.resp, s.ref = None, None, None, "no model", None, None, None, None

    def abort(s):  # unblock a thread stuck reading the stream (used on quit)
        try: s.resp.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except Exception: pass

    def stop(s):
        if s.proc and s.proc.poll() is None:
            s.proc.terminate()
            try: s.proc.wait(5)
            except subprocess.TimeoutExpired: s.proc.kill()
        s.proc, s.url = None, None

    def start(s, kind, ref):
        s.stop(); s.ctx, s.kind, s.ref = None, kind, ref
        if kind == "ollama":
            s.url, s.model, s.name = f"{OLLAMA}/v1", ref, ref; return
        if kind == "url":
            s.url = ref.rstrip("/") + ("" if ref.rstrip("/").endswith("/v1") else "/v1")
            s.model = json.loads(get(s.url + "/models", timeout=5))["data"][0]["id"]; s.name = s.model; return
        port = free_port()
        if kind == "gguf":
            src = ["-m", ref] if Path(ref).exists() else ["-hf", ref]
            mm = sorted(Path(ref).parent.glob("*mmproj*.gguf"), key=lambda p: ("f32" in p.name.lower(), p.stat().st_size)) if Path(ref).exists() else []
            cmd = [which("llama-server"), *src, *(["--mmproj", str(mm[0])] if mm else []), "--jinja", "-c", str(CTX), "--port", str(port)]
            s.model, s.name, s.ctx, health = "local", Path(ref).name.removesuffix(".gguf"), CTX, "/health"
        else:  # mlx
            cmd = [sys.executable, "-m", "mlx_lm.server"] if importlib.util.find_spec("mlx_lm") else [which("mlx_lm.server")]
            cmd += ["--model", ref, "--port", str(port)]
            s.model, s.name, health = ref, ref.split("/")[-1], "/v1/models"
        DIR.mkdir(parents=True, exist_ok=True)
        log = open(DIR / "server.log", "w")
        s.proc = spawn(cmd, stdout=log, stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{port}"
        for _ in range(1200):
            if s.proc.poll() is not None:
                tail = (DIR / "server.log").read_text(errors="replace").strip().splitlines()[-3:]
                raise RuntimeError("server exited: " + " / ".join(tail))
            try: get(base + health, timeout=1); break
            except Exception: time.sleep(0.5)
        else: raise RuntimeError("server start timed out")
        s.url = base + "/v1"

    def stream(s, msgs, native, stop):
        body = {"model": s.model, "messages": msgs, "stream": True, "stream_options": {"include_usage": True}}
        if native: body["tools"] = TOOLS
        req = urllib.request.Request(s.url + "/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        try: r = urllib.request.urlopen(req, timeout=900)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{e.code}: {e.read().decode(errors='replace')[:400]}") from None
        s.resp = r
        with r:
            for line in r:
                if stop.is_set(): return
                line = line.strip()
                if line.startswith(b"data:"):
                    d = line[5:].strip()
                    if d == b"[DONE]": return
                    yield json.loads(d)
