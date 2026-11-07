# minu

A very small agent harness for local models. One tool (`sh`) and a system prompt of about 86 tokens.

```
uv run minu                       # opens the model picker
uv run minu --hf LiquidAI/LFM3-1.7B-GGUF
uv run minu --mlx mlx-community/Qwen3-1.7B-4bit
uv run minu --ollama gemma3:4b
uv run minu --url http://localhost:8080           # server that's already running
```
Install the `minu` command globally (changes to `src/` apply right away):
```
git clone https://github.com/mr-jones123/minu && cd minu
uv tool install -e .
```
Then run `minu` in any project folder. To uninstall: `uv tool uninstall minu`.

`-y` runs commands without asking. `--native` uses the server's tool-call API instead of ```sh blocks.

## Models
`ctrl+o` (or `/model`) opens the picker. It has:
- the GGUF and MLX models in your Hugging Face cache, plus your Ollama models
- **⬇ download from Hugging Face**: search, or paste `org/repo`, then pick a size. For vision repos the `mmproj` file is downloaded too.
- **⬇ pull from Ollama**: any name from ollama.com/library, with progress shown in the status bar.

Switching models stops the old server and starts the new one. The chat stays.
`esc` cancels a download.

If something is missing, minu offers to install it (it always asks first):
| needed for | tool | install |
|---|---|---|
| GGUF | llama-server | `brew install llama.cpp` |
| MLX (Apple Silicon only) | mlx_lm | `uv tool install mlx-lm` |
| HF downloads | hf | `uv tool install huggingface_hub` |
| Ollama | ollama | `brew install ollama` / ollama.com install script |

If Ollama is installed but not running, minu starts `ollama serve` itself and stops it when you quit.

## Images
Put an image path in your message (dragging a file into the terminal pastes its path):
`what's in ~/Desktop/shot.png?`
The image is shown in the chat and sent to the model. That needs a vision model: GGUF repos with an
mmproj (marked `[vision]` in the picker), or an Ollama vision model such as `gemma3:4b`. MLX models are text only.
Image files the model mentions in its answer are shown too, and `/view path.png` shows any image.
Images render as real pixels in Kitty, Ghostty, WezTerm and iTerm2, and as colored blocks in other terminals.

## Sessions
Each chat is saved to `~/.minu/sessions/<project>/<timestamp>.jsonl` (one folder per project path, e.g.
`-Users-me-code-app`): a `{"meta": …}` line, then one message per line. Set `MINU_HOME` to move `~/.minu`.
Sessions from older versions in `./.minu/sessions` still show up in `/resume`.
`/resume` opens a session picker · `minu -c` continues the latest one · `minu -r FILE` opens a specific file · `/new` (or `ctrl+n`) starts a new session.

## Keys
`enter` send · `ctrl+j` newline · `ctrl+o` model · `ctrl+y` auto-run · `esc` stop · `ctrl+n` new session · `ctrl+c` quit
Type `/` for a menu of commands (↑/↓ to move, tab to complete, enter to run, esc to close):
`/new` `/model` `/resume` `/search <query>` `/fetch <url>` `/view <img>` `/auto` `/clear` `/exit`

## Web
The model can search on its own (`minu-search "q"`, `minu-fetch URL` in its shell). You can also do it yourself:
`/search <query>` gets results and the model answers from them; `/fetch <url>` reads a page and the model summarizes it.
Search tries DuckDuckGo first, then Wikipedia's API. DuckDuckGo sometimes rate-limits; for search that never gets blocked,
point minu at your own SearXNG instance: `MINU_SEARXNG=http://localhost:8888`.
Env: `MINU_CTX` (llama.cpp context, default 16384), `MINU_HOME` (default `~/.minu`), `OLLAMA_HOST`, `HF_HOME`. Server log: `~/.cache/minu/server.log`.

## Code layout (`src/`, installed as the `minu` package)
| file | what it does |
|---|---|
| `cli.py` | command-line flags, plus `minu search` / `minu fetch` for the agent's shell |
| `config.py` | paths, limits, system prompts, banner |
| `app.py` | the TUI: layout, status bar, input handling |
| `agent.py` | agent loop: stream a reply, run its command, send the output back |
| `model_flows.py` | model picker, HF/Ollama downloads, install offers, loading |
| `sessions.py` | saving and resuming `~/.minu/sessions/<project>/*.jsonl` |
| `server.py` | starting llama-server / mlx_lm / Ollama and streaming chat |
| `models.py` | finding local models and searching Hugging Face |
| `tools.py` | the `sh` tool, web search/fetch, parsing commands from replies |
| `images.py` | attaching images and showing them |
| `installs.py` | finding tools and their install commands |
| `widgets.py` | input box, list picker, text prompt |
