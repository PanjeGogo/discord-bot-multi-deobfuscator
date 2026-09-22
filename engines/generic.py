"""Shared bounded static rewrite helpers.

These helpers never execute uploaded Lua/Luau.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class LocalResult:
    source: str
    changed: bool
    notes: list[str]


_NUM_EXPR = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*([+\-*/%])\s*(-?\d+(?:\.\d+)?)(?![\w.])")
_STR_CAT = re.compile(r'(["\'])(.*?)\1\s*\.\.\s*(["\'])(.*?)\3')


def _fold_numbers(source: str) -> tuple[str, bool]:
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
            else: return m.group(0)
            return str(int(z)) if z.is_integer() else repr(z)
        except Exception:
            return m.group(0)
    out = _NUM_EXPR.sub(repl, source)
    return out, out != source


def _fold_strings(source: str) -> tuple[str, bool]:
    def repl(m):
        q1, a, q2, b = m.groups()
        return q1 + a + b + q1 if q1 == q2 else m.group(0)
    out = _STR_CAT.sub(repl, source)
    return out, out != source


def rewrite(source: str, max_steps: int = 4) -> LocalResult:
    cur, notes = source, []
    for _ in range(max_steps):
        changed = False
        cur, c = _fold_strings(cur)
        if c:
            changed = True
            notes.append("constant string concatenation")
        cur, c = _fold_numbers(cur)
        if c:
            changed = True
            notes.append("numeric constant folding")
        if not changed:
            break
    return LocalResult(cur, cur != source, list(dict.fromkeys(notes)))
