"""minu: a tiny agent harness for local models (llama.cpp / MLX / Ollama)."""
from importlib.metadata import PackageNotFoundError, version

try: __version__ = version("minu")
except PackageNotFoundError: __version__ = "0.0.0"
