"""Picking, downloading, installing and loading models (mixed into the app)."""
import asyncio, importlib.util, json, re, subprocess, time, urllib.request
from pathlib import Path

from textual import work

from .config import MLX_OK, OLLAMA
from .installs import install_cmd, which
from .server import spawn
from .models import discover, hf_files, hf_search, ollama_up
from .widgets import Ask, Picker


class ModelFlowsMixin:
    @work(exclusive=True, group="pick")
    async def action_pick(s):
        if which("ollama") and not await asyncio.to_thread(ollama_up):
            await asyncio.to_thread(s.start_ollama)
        items = [("⬇  download from Hugging Face…", ("dl-hf", None)),
                 ("⬇  pull from Ollama…", ("dl-ollama", None))] + await asyncio.to_thread(discover)
        choice = await s.push_screen_wait(Picker("models", items))
        if not choice: return
        kind, ref = choice
        if kind == "dl-ollama":
            name = await s.push_screen_wait(Ask("Ollama model to pull (see ollama.com/library)", "e.g. qwen3:4b, gemma3:4b (vision)"))
            if name: s.pull_ollama(name)
        elif kind == "dl-hf":
            await s.hf_flow()
        else:
            s.load(kind, ref)

    async def hf_flow(s):
        q = await s.push_screen_wait(Ask("Search Hugging Face, or paste org/repo", "e.g. qwen3 gguf, gemma 3 mlx, ggml-org/SmolVLM-256M-Instruct-GGUF"))
        if not q: return
        try:
            if "/" in q: repo = q.removeprefix("https://huggingface.co/").strip("/")
            else:
                s.state = "searching…"; s.status()
                res = await asyncio.to_thread(hf_search, q); s.state = ""; s.status()
                if not res: return s.notify(f"no GGUF/MLX models for '{q}'")
                repo = await s.push_screen_wait(Picker(f"results for '{q}'", res))
                if not repo: return
            kind, gg, mm, files = await asyncio.to_thread(hf_files, repo)
        except Exception as e:
            s.state = ""; s.status(); return s.note(f"▸ Hugging Face error: {e}")
        if kind is None: return s.note(f"▸ {repo} has no GGUF or MLX weights; minu can't run it")
        if kind == "mlx":
            if not MLX_OK: return s.note("▸ MLX models need an Apple Silicon Mac")
            return s.download_hf(repo, [], kind)
        pref = lambda f: (not re.search(r"q4_k_m", f, re.I), gg[f])
        opts = [(f"{f}  {gg[f] / 1e9:.1f} GB", f) for f in sorted(gg, key=pref)]
        f = opts[0][1] if len(opts) == 1 else await s.push_screen_wait(Picker(f"{repo}: pick a size (Q4_K_M is a good default)", opts))
        if not f: return
        part = re.split(r"-00001-of-", f)[0]
        want = [g for g in files if g.startswith(part) and g.endswith(".gguf")] if "-00001-of-" in f else [f]
        if mm:  # vision projector: prefer Q8/f16 over f32
            want.append(sorted(mm, key=lambda m: ("f32" in m.lower(), mm[m]))[0])
        s.download_hf(repo, want, kind)

    def need(s, tool):  # path to tool, offering to install it if missing
        if p := which(tool): return p
        cmd, hint = install_cmd(tool)
        if not cmd:
            s.say(f"▸ {tool} isn't installed and minu can't install it here. See {hint}"); return None
        if not s.ask(f"{tool} isn't installed. Install it with `{cmd}`?"):
            s.say(f"▸ skipped. To install later: {cmd}"); return None
        rc, tail = s.proc(cmd, f"installing {tool}")
        if rc != 0 or not which(tool):
            s.say("▸ install failed:\n" + "\n".join(tail[-5:]) + f"\nSee {hint}"); return None
        s.say(f"▸ installed {tool}"); return which(tool)

    def start_ollama(s, ask=False):
        if ollama_up(): return True
        exe = s.need("ollama") if ask else which("ollama")
        if not exe: return False
        s.ollama_proc = spawn([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if ollama_up(): return True
            time.sleep(0.25)
        return False

    def _load(s, kind, ref):
        s.set_state(f"loading {Path(ref).name}…")
        try:
            if kind == "gguf" and not s.need("llama-server"): raise RuntimeError("llama-server is required for GGUF models")
            if kind == "mlx" and not importlib.util.find_spec("mlx_lm") and not s.need("mlx_lm.server"):
                raise RuntimeError("mlx-lm is required for MLX models")
            if kind == "ollama" and not s.start_ollama(ask=True): raise RuntimeError("Ollama isn't running")
            s.set_state(f"loading {Path(ref).name}…")
            s.srv.start(kind, ref); s.say(f"▸ model: {s.srv.name} ({kind})")
        except Exception as e:
            s.srv.name = "no model"; s.say(f"▸ failed: {e}")
        s.set_state("")

    @work(thread=True, exclusive=True, group="load")
    def load(s, kind, ref): s._load(kind, ref)

    @work(thread=True, exclusive=True, group="load")
    def download_hf(s, repo, files, kind):
        s.stop_ev.clear()
        if not (exe := s.need("hf")): return
        s.say(f"▸ downloading {repo} {' '.join(files)}  (esc to cancel)")
        rc, tail = s.proc([exe, "download", repo, *files], f"↓ {repo.split('/')[-1]}")
        if rc != 0:
            why = "\n".join(tail[-4:])
            if re.search(r"401|403|gated|restricted", why, re.I): why += "\nThis repo needs a login: run `hf auth login`, then accept its license on huggingface.co"
            return s.say(f"▸ download failed:\n{why}")
        if kind == "mlx": return s._load("mlx", repo)
        for _, (k, ref) in discover():
            if k == "gguf" and ref.endswith(Path(files[0]).name): return s._load("gguf", ref)
        s.say("▸ downloaded, but couldn't find the file in the HF cache (ctrl+o to pick it)")

    @work(thread=True, exclusive=True, group="load")
    def pull_ollama(s, name):
        s.stop_ev.clear()
        if not s.start_ollama(ask=True): return s.say("▸ Ollama isn't running")
        s.say(f"▸ pulling {name} from Ollama  (esc to cancel)")
        req = urllib.request.Request(f"{OLLAMA}/api/pull", json.dumps({"model": name}).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3600) as r:
                for line in r:
                    if s.stop_ev.is_set(): s.set_state(""); return s.say("▸ pull cancelled")
                    j = json.loads(line)
                    if "error" in j: raise RuntimeError(j["error"])
                    pct = f" {100 * j['completed'] // j['total']}%" if j.get("total") and j.get("completed") else ""
                    s.set_state(f"↓ {name}: {j.get('status', '')}{pct}")
        except Exception as e:
            s.set_state(""); return s.say(f"▸ pull failed: {e}")
        s._load("ollama", name)
