"""Finding local models (HF cache, Ollama) and searching Hugging Face."""
import json, re, shutil, urllib.parse, urllib.request
from pathlib import Path

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

def gb(n): return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.0f} MB"

def _repo_dir(p):  # .../hub/models--org--name/snapshots/<rev>/x.gguf -> .../hub/models--org--name
    return next(d for d in Path(p).parents if d.name.startswith("models--"))

def _shards(p):  # a .gguf plus its -0000N-of-M siblings
    p = Path(p)
    if not (m := re.match(r"(.*)-00001-of-(\d+)\.gguf$", p.name)): return [p]
    return sorted(p.parent.glob(f"{m[1]}-*-of-{m[2]}.gguf"))

def _du(d): return sum(f.stat().st_size for f in Path(d).rglob("*") if f.is_file() and not f.is_symlink())

def deletable():  # (label, (kind, ref, name, bytes)) for everything minu can delete
    out = []
    for label, (kind, ref) in discover():
        if kind == "gguf":
            n = sum(f.resolve().stat().st_size for f in _shards(ref) if f.exists())
            name = f"{_repo_dir(ref).name[8:].replace('--', '/')} · {Path(ref).name}"
        elif kind == "mlx":
            n, name = _du(HF / ("models--" + ref.replace("/", "--"))), ref
        else: continue
        out.append((f"{gb(n):>8}  {label}", (kind, ref, name, n)))
    try:
        for m in json.loads(get(f"{OLLAMA}/api/tags", timeout=1))["models"]:
            out.append((f"{gb(m.get('size', 0)):>8}  ollama  {m['name']}", ("ollama", m["name"], m["name"], m.get("size", 0))))
    except Exception: pass
    return out

def delete_model(kind, ref):  # -> what was removed
    if kind == "ollama":
        req = urllib.request.Request(f"{OLLAMA}/api/delete", json.dumps({"model": ref}).encode(),
                                     {"Content-Type": "application/json"}, method="DELETE")
        urllib.request.urlopen(req, timeout=30).close(); return f"ollama model {ref}"
    if kind == "mlx":
        repo = HF / ("models--" + ref.replace("/", "--"))
    else:  # one quant of a GGUF repo: drop it, and the whole repo once no model weights are left
        repo = _repo_dir(ref)
        rels = [f.relative_to(next(d for d in f.parents if d.parent.name == "snapshots")) for f in _shards(ref)]
        links = [g for rel in rels for g in repo.glob(f"snapshots/*/{rel}")]  # same file in every revision
        blobs = {g.resolve() for g in links}
        for g in links: g.unlink(missing_ok=True)
        used = {g.resolve() for g in repo.glob("snapshots/*/**/*") if g.is_symlink()}
        for b in blobs - used:
            if b.exists() and b.parent.name == "blobs": b.unlink()
        left = [g for g in repo.glob("snapshots/*/**/*.gguf") if "mmproj" not in g.name.lower()]
        if left: return Path(ref).name
    if HF not in repo.parents: raise RuntimeError(f"refusing to delete {repo}: not in the HF cache")
    shutil.rmtree(repo); shutil.rmtree(HF / ".locks" / repo.name, ignore_errors=True)
    return repo.name[8:].replace("--", "/")

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
