"""Local static deobfuscation engines.

Engines are selected by the detected obfuscator family. They never execute
uploaded Lua/Luau.
"""
from .registry import analyze_and_rewrite

__all__ = ["analyze_and_rewrite"]
