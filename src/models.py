"""Finding local models (HF cache, Ollama) and searching Hugging Face."""
import json, re, urllib.parse

from .config import HF, MLX_OK, OLLAMA
from .tools import get

def ollama_up():
    try: get(f"{OLLAMA}/api/tags", timeout=1); return True
    except Exception: return False

def discover():
    ms = []  # (label, (kind, ref))
    for d in sorted(HF.glob("models--*")) if HF.is_dir() else []:
        repo = d.name[8:].replace("--", "/")
        ggufs = {p.name: p for p in d.glob("snapshots/*/**/*.gguf")
                 if "mmproj" not in p.name.lower() and not re.search(r"-0000[2-9]-of-", p.name)}
        for n, p in sorted(ggufs.items()):
            eye = " [vision]" if any(p.parent.glob("*mmproj*.gguf")) else ""
            ms.append((f"gguf    {repo} · {n}{eye}", ("gguf", str(p))))
        cfg = next(d.glob("snapshots/*/config.json"), None)
        if not ggufs and cfg and ("mlx" in repo.lower() or "quantization" in cfg.read_text()):
            ms.append((f"mlx     {repo}", ("mlx", repo)))
    try:
        for m in json.loads(get(f"{OLLAMA}/api/tags", timeout=1))["models"]:
            ms.append((f"ollama  {m['name']}", ("ollama", m["name"])))
    except Exception:
        pass
    return ms

def hf_api(path):
    return json.loads(get("https://huggingface.co/api/" + path, timeout=15))

def hf_search(q):
    out, kinds = [], ["gguf"] + (["mlx"] if MLX_OK else [])
    for k in kinds:
        for m in hf_api(f"models?search={urllib.parse.quote(q)}&filter={k}&sort=downloads&limit=15"):
            out.append((m.get("downloads", 0), k, m["id"]))
    out.sort(reverse=True)
    return [(f"{k:5} {i}  ↓{n:,}", i) for n, k, i in out]

def hf_files(repo):
    info = hf_api(f"models/{repo}?blobs=true")
    files = {s["rfilename"]: s.get("size") or 0 for s in info.get("siblings", [])}
    gg, mm = {}, {}
    for f, sz in files.items():
        if not f.endswith(".gguf"): continue
        if "mmproj" in f.lower(): mm[f] = sz; continue
        if re.search(r"-0000[2-9]-of-", f): continue
        part = re.split(r"-00001-of-", f)[0]
        gg[f] = sum(z for g, z in files.items() if g.startswith(part)) if "-00001-of-" in f else sz
    tags = info.get("tags", [])
    kind = "gguf" if gg else ("mlx" if "mlx" in tags or "mlx" in repo.lower() else None)
    return kind, gg, mm, files
