"""Where tools live, and how to install them when they are missing."""
import platform, shutil, sys

from .config import HOME, MLX_OK

def which(tool):
    return shutil.which(tool) or shutil.which(tool, path=f"{HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin")

def install_cmd(tool):  # -> (command or None, help)
    brew, uv = which("brew"), which("uv")
    pip = lambda pkg: f"uv tool install {pkg}" if uv else f"{sys.executable} -m pip install -U {pkg}"
    if tool == "llama-server":
        return ("brew install llama.cpp" if brew else None), "https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md"
    if tool == "ollama":
        if platform.system() == "Linux": return "curl -fsSL https://ollama.com/install.sh | sh", "https://ollama.com/download"
        return ("brew install ollama" if brew else None), "https://ollama.com/download"
    if tool == "hf":
        return pip("huggingface_hub"), "https://huggingface.co/docs/huggingface_hub/installation"
    if tool == "mlx_lm.server":
        return (pip("mlx-lm") if MLX_OK else None), "MLX needs an Apple Silicon Mac"
    return None, ""
