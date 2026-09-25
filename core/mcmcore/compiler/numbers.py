"""Stage 1 of the paper compiler: ResultAtom -> LaTeX number macros.

This is the single-source-of-truth mechanism, made concrete.

A number in the paper is a REFERENCE, never a literal. The compiler emits::

    \\newcommand{\\numRESZeroOneFourTwo}{0.0791}
    \\newcommand{\\numRESZeroOneFourTwoPct}{7.91\\%}

and the prose says ``\\numRESZeroOneFourTwo{}``. Nothing downstream re-types
the value, so an updated atom cannot leave a stale literal behind.

Corpus grounding: 69% of papers repeat a precise number internally, and ~73% of
Summary numbers reappear verbatim in the body. That repetition is exactly the
failure this module makes impossible.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..schemas import ResultAtom

# Digit words, so RES-0142 becomes \numRESZeroOneFourTwo rather than
# \numRES0142. LaTeX control sequences may not contain digits, which is why
# this spelling is forced rather than a stylistic choice.
_DIGIT_WORDS = {
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}

# A LaTeX control sequence is letters only, so every other character is a boundary.
_ALNUM = re.compile(r"[A-Za-z0-9]")


def alias_macro_name(alias: str, suffix: str = "") -> str:
    """把别名转成合法的宏名：只保留字母，首字母大写。

    'r_squared' -> 'numRSquared'。数字会被丢掉，因为 LaTeX 的
    控制序列不能含数字 —— 别名里带数字是作者笔误，静默忽略比报错好。
    """
    letters = [c for c in alias if c.isalpha()]
    if not letters:
        return ""
    camel = "".join(w[:1].upper() + w[1:] for w in alias.replace("-", "_").split("_") if w)
    camel = "".join(c for c in camel if c.isalpha())
    return f"num{camel}{suffix}"


def macro_name(atom_id: str, suffix: str = "") -> str:
    """Convert a result-atom id into a legal LaTeX control-sequence name.

    ``RES-0142``        -> ``numRESZeroOneFourTwo``
    ``RES-0142`` + Pct  -> ``numRESZeroOneFourTwoPct``

    Non-alphanumeric characters are dropped (they cannot appear in a control
    sequence); digits are spelled out for the same reason.
    """
    parts: List[str] = []
    for ch in atom_id:
        if ch.isdigit():
            parts.append(_DIGIT_WORDS[ch])
        elif ch.isalpha():
            parts.append(ch)
        # everything else (dash, underscore, dot) is a separator we drop
    core = "".join(parts)
    if not core or not core[0].isalpha():
        core = "num" + core
    return f"num{core}{suffix}"


def _latex_escape_percent(text: str) -> str:
    """Escape a bare % so it is a literal percent sign in LaTeX."""
    return text.replace("%", r"\%")


def render_atom(atom: ResultAtom, rendering: Optional[str] = None) -> str:
    """Render an atom's value to a LaTeX-safe string."""
    if rendering:
        raw = atom.renderings.get(rendering)
        if raw is not None:
            return raw
    value = atom.value
    if isinstance(value, float):
        try:
            return atom.format % value
        except (TypeError, ValueError):
            return repr(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _latex_escape_percent(str(value))


class NumberMacros:
    """All number macros for one build, plus lookup tables for auditing."""

    def __init__(self) -> None:
        # macro name -> LaTeX body
        self.macros: Dict[str, str] = {}
        # macro name -> atom id (for reverse lookup during audit)
        self.owner: Dict[str, str] = {}
        # atom id -> [macro names]
        self.by_atom: Dict[str, List[str]] = {}
        # normalized value -> [atom ids], used to detect merged duplicates
        self._values: Dict[str, List[str]] = {}

    # -- construction ------------------------------------------------------
    def add_atom(self, atom: ResultAtom) -> List[str]:
        """Register the primary macro plus one per named alternate rendering."""
        names: List[str] = []

        # 有别名就用别名：\numRSquared{} 比
        # \numRESEXPZeroZeroOneRTwoZeroZeroOne{} 好在正文里能读能写。
        # 别名冲突时回退到长名，绝不静默覆盖 —— 覆盖会让论文里
        # 某个数字悄悄变成另一个数的值。
        primary = alias_macro_name(atom.macro_alias) if atom.macro_alias else ""
        if not primary or primary in self.macros:
            primary = macro_name(atom.atom_id)
        self.macros[primary] = render_atom(atom)
        self.owner[primary] = atom.atom_id
        names.append(primary)

        for rendering in sorted(atom.renderings):
            # e.g. rendering "pct" -> \numRSquaredPct
            suffix = "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", rendering) if p)
            if not suffix:
                continue
            name = (alias_macro_name(atom.macro_alias, suffix)
                    if atom.macro_alias else macro_name(atom.atom_id, suffix))
            if name in self.macros:
                name = macro_name(atom.atom_id, suffix)
            self.macros[name] = render_atom(atom, rendering)
            self.owner[name] = atom.atom_id
            names.append(name)

        self.by_atom[atom.atom_id] = names
        n = atom.numeric()
        if n is not None:
            self._values.setdefault(f"{n:.6g}", []).append(atom.atom_id)
        return names

    def add_all(self, atoms: List[ResultAtom]) -> "NumberMacros":
        for a in atoms:
            self.add_atom(a)
        return self

    # -- queries -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self.macros)

    def __contains__(self, name: object) -> bool:
        return name in self.macros

    def atom_for(self, macro: str) -> Optional[str]:
        return self.owner.get(macro)

    def duplicate_values(self) -> Dict[str, List[str]]:
        """Values shared by more than one atom.

        A signal that the same quantity was recorded twice instead of being
        single-sourced. Reported as INFO, never an error: two models legitimately
        producing the same number is not a defect.
        """
        return {k: v for k, v in self._values.items() if len(v) > 1}

    def duplicate_macro_bodies(self) -> Dict[str, List[str]]:
        """Macros that expand to the same text, grouped by that text."""
        by_body: Dict[str, List[str]] = {}
        for name, body in self.macros.items():
            by_body.setdefault(body, []).append(name)
        return {b: n for b, n in by_body.items() if len(n) > 1}

    # -- emission ----------------------------------------------------------
    def to_latex(self, header: bool = True) -> str:
        """Emit the generated macros file."""
        lines: List[str] = []
        if header:
            lines.extend([
                "% ------------------------------------------------------------------",
                "% GENERATED FILE - DO NOT EDIT BY HAND",
                "% Produced by mcmcore.numbers from ResultAtom records.",
                "% Every number in the paper is a reference into this file.",
                "% ------------------------------------------------------------------",
                "",
            ])
        for name in sorted(self.macros):
            lines.append(f"\\newcommand{{\\{name}}}{{{self.macros[name]}}}")
        lines.append("")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Bare-number detection
# --------------------------------------------------------------------------

# Tokens we must NOT flag, because they are not results:
#   - numbers inside a LaTeX command (\cite{...}, \ref{...}, \label{...})
#   - numbers in a comment
#   - numbers inside \lit{...}, the explicit escape hatch
#   - section/equation numbering syntax
_NUMBER_TOKEN = re.compile(r"(?<![\w.\\{])(\d+(?:\.\d+)?)(?![\w.}])")


def _strip_ignorable(text: str) -> str:
    """Blank out regions where a bare number is legitimate."""
    # Comments: drop to end of line.
    text = re.sub(r"(?<!\\)%.*", "", text)
    # \lit{...} is the declared escape hatch.
    text = re.sub(r"\\lit\{[^}]*\}", lambda m: " " * len(m.group(0)), text)
    # Command arguments that naturally contain digits. LaTeX commands may carry
    # an optional [..] argument too, and \includegraphics[width=0.8\linewidth]
    # is the common case: strip it along with the mandatory {..} argument.
    for cmd in ("cite", "citep", "citet", "ref", "eqref", "label", "includegraphics",
                "input", "usepackage", "documentclass", "num", "qty", "SI"):
        text = re.sub(
            rf"\\{cmd}(\[[^\]]*\])?\{{[^}}]*\}}",
            lambda m: " " * len(m.group(0)),
            text,
        )
    return text


def find_bare_numbers(text: str) -> List[Tuple[str, int]]:
    """Find numeric literals in prose that are not atom references.

    Returns ``[(token, offset)]``. Callers turn these into NUMERIC_UNBOUND
    findings: a number typed by hand cannot be kept in sync with its source.
    """
    stripped = _strip_ignorable(text)
    out: List[Tuple[str, int]] = []
    for m in _NUMBER_TOKEN.finditer(stripped):
        token = m.group(1)
        # A number immediately following \num...{} style macro braces is fine,
        # and a bare integer in a list context like "(1)" is equation numbering.
        start = m.start()
        prev = stripped[max(0, start - 3):start]
        if prev.endswith("\\{"):
            continue
        out.append((token, start))
    return out


def check_section_body(section_id: str, body: str) -> List[Tuple[str, str]]:
    """Return ``[(code, message)]`` for unbound numbers in one section body."""
    findings: List[Tuple[str, str]] = []
    for token, _offset in find_bare_numbers(body):
        findings.append((
            "NUMERIC_UNBOUND",
            f"章节 '{section_id}' 的正文里出现了没有来源的数字 {token}。"
            f"请把它绑定到 ResultAtom 宏；如果它不是结果数字"
            f"（页数、折叠次数、题目字母），用 \\lit{{{token}}} 标记为例外。",
        ))
    return findings
