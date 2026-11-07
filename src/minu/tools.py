"""The agent's shell tool, web search/fetch, and parsing commands out of replies."""
import html, json, os, re, shlex, subprocess, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

from .config import DIR, HOME, OUT_MAX, UA

def get(url, data=None, timeout=20, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

class _Text(HTMLParser):
    SKIP, BR = {"script", "style", "noscript", "svg", "head"}, {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "pre"}
    def __init__(s): super().__init__(); s.out, s.skip = [], 0
    def handle_starttag(s, t, a):
        if t in s.SKIP: s.skip += 1
        elif t in s.BR: s.out.append("\n")
    def handle_endtag(s, t):
        if t in s.SKIP and s.skip: s.skip -= 1
    def handle_data(s, d):
        if not s.skip: s.out.append(d)

def fetch(url):
    p = _Text(); p.feed(get(url))
    t = re.sub(r"[ \t]+", " ", "".join(p.out))
    return re.sub(r"\s*\n\s*", "\n", t).strip()[:8000]

def _ddg(q):
    for _ in range(2):  # DuckDuckGo throttles bursts; retry once
        h = get("https://html.duckduckgo.com/html/", urllib.parse.urlencode({"q": q}).encode())
        if "result__a" in h: break
        time.sleep(2)
    out = []
    for u, t, s in re.findall(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', h, re.S):
        out.append((t, urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(u)).query).get("uddg", [u])[0], s))
    return out

def _wikipedia(q):
    j = json.loads(get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 5})))
    return [(r["title"], "https://en.wikipedia.org/wiki/" + urllib.parse.quote(r["title"].replace(" ", "_")), r["snippet"])
            for r in j["query"]["search"]]

def _searxng(q):  # optional: MINU_SEARXNG=https://your-instance
    j = json.loads(get(os.environ["MINU_SEARXNG"].rstrip("/") + "/search?" + urllib.parse.urlencode({"q": q, "format": "json"})))
    return [(r.get("title", ""), r.get("url", ""), r.get("content", "")) for r in j.get("results", [])]

def search(q):  # first engine that answers wins
    clean = lambda x: html.unescape(re.sub(r"<.*?>", "", x)).strip()
    engines = ([_searxng] if os.environ.get("MINU_SEARXNG") else []) + [_ddg, _wikipedia]
    for engine in engines:
        try: res = engine(q)
        except Exception: res = []
        if res:
            return f"[{engine.__name__[1:]}]\n\n" + "\n\n".join(f"{clean(t)}\n{u}\n{clean(s)}" for t, u, s in res[:8])
    return "search failed: no engine answered (rate-limited?). Try again shortly, or minu-fetch a URL you know."

def shims():
    (DIR / "bin").mkdir(parents=True, exist_ok=True)
    for n in ("search", "fetch"):
        p = DIR / "bin" / f"minu-{n}"
        p.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m minu {n} "$*"\n'); p.chmod(0o755)

def sh_env():
    return {**os.environ, "PATH": f"{DIR / 'bin'}:{os.environ['PATH']}:{HOME}/.local/bin"}

def sh(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                           env=sh_env(), executable="/bin/bash", stdin=subprocess.DEVNULL)
        out = (r.stdout + r.stderr).strip() + ("" if r.returncode == 0 else f"\n[exit {r.returncode}]")
    except subprocess.TimeoutExpired:
        out = f"[timed out after {timeout}s]"
    out = out.strip() or "[no output]"
    if len(out) > OUT_MAX:
        out = out[:OUT_MAX // 2] + f"\n...[{len(out) - OUT_MAX} chars cut]...\n" + out[-OUT_MAX // 2:]
    return out

def to_cmd(m):  # ```sh block, or a model's own <tool_call> / JSON call -> shell command
    if m.group(1) is not None: return m.group(1).strip()
    t = m.group(2).strip()
    try:
        j = json.loads(t); name, args = j.get("name", ""), j.get("arguments") or {}
    except json.JSONDecodeError:
        name = (re.search(r"<function=([^>\s]+)>", t) or re.search(r"(\S+)", t)).group(1)
        args = dict(re.findall(r"<parameter=([^>]+)>\s*(.*?)\s*</parameter>", t, re.S))
    if isinstance(args, str): args = {"command": args}
    if name in ("sh", "bash", "shell", "run", "exec", "terminal") or "command" in args:
        return str(args.get("command") or next(iter(args.values()), ""))
    return " ".join([name, *(shlex.quote(str(v)) for v in args.values())])

def split_think(t):  # reply -> (thinking, answer); handles an unclosed <think> while streaming
    head = t.split("</think>")[0]
    if "</think>" in t and "<think>" not in head: t = "<think>" + t  # chat template already opened <think>
    think = "".join(re.findall(r"<think>(.*?)</think>", t, re.S))
    rest = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    if "<think>" in rest: rest, tail = rest.split("<think>", 1); think += tail
    return think.strip(), rest.strip()

def strip_think(t): return split_think(t)[1]
