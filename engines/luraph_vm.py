"""Local, non-executing Luraph VM analysis helpers.

This module intentionally does NOT execute uploaded Lua/Luau. It performs
bounded static rewrites and VM-shape extraction so common obfuscation layers
can be removed before Gemini is contacted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class LocalResult:
    source: str
    changed: bool
    notes: list[str]


_NUM_EXPR = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*([+\-*/%%])\s*(-?\d+(?:\.\d+)?)(?![\w.])")
_STR_CAT = re.compile(r'(["\'])(.*?)\1\s*\.\.\s*(["\'])(.*?)\3')


def _safe_number_folding(source: str) -> tuple[str, bool]:
    def repl(m):
        a, op, b = m.group(1), m.group(2), m.group(3)
        try:
            x, y = float(a), float(b)
            if op == "+": z = x + y
            elif op == "-": z = x - y
            elif op == "*": z = x * y
            elif op == "/":
                if y == 0: return m.group(0)
                z = x / y
            elif op == "%":
                if y == 0: return m.group(0)
                z = x % y
            else: return m.group(0)
            if z.is_integer(): return str(int(z))
            return repr(z)
        except Exception:
            return m.group(0)
    out = _NUM_EXPR.sub(repl, source)
    return out, out != source


def _safe_string_concat(source: str) -> tuple[str, bool]:
    def repl(m):
        q1, a, q2, b = m.groups()
        if q1 != q2: return m.group(0)
        return q1 + a + b + q1
    out = _STR_CAT.sub(repl, source)
    return out, out != source


def analyze_and_rewrite(source: str, family: str, max_steps: int = 4) -> LocalResult:
    if family != "luraph_v14":
        return LocalResult(source, False, [])

    cur = source
    notes = []
    for _ in range(max_steps):
        changed = False
        cur, c = _safe_string_concat(cur)
        if c:
            changed = True
            notes.append("constant string concatenation")
        cur, c = _safe_number_folding(cur)
        if c:
            changed = True
            notes.append("numeric constant folding")
        if not changed:
            break

    # Collect VM-like indicators for observability; never execute them.
    vm_hits = 0
    vm_hits += len(re.findall(r"\b(?:bit32|bit)\.(?:bxor|band|bor|lshift|rshift)\b", cur))
    vm_hits += len(re.findall(r"\[[^\]]+\]\s*=\s*[^\n]+", cur))
    if vm_hits:
        notes.append(f"VM-like operations observed: {vm_hits}")

    return LocalResult(cur, cur != source, list(dict.fromkeys(notes)))
