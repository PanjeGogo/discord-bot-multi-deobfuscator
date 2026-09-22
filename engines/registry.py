"""Engine registry for multi-obfuscator local analysis."""
from __future__ import annotations

from .luraph import analyze_and_rewrite as analyze_luraph
from .generic import rewrite as generic_rewrite

ENGINES = {
    "luraph_v14": analyze_luraph,
    "generic": generic_rewrite,
}


def analyze_and_rewrite(source: str, family: str, max_steps: int = 4):
    engine = ENGINES.get(family, generic_rewrite)
    if family == "luraph_v14":
        return engine(source, max_steps=max_steps)
    return engine(source, max_steps=max_steps)
