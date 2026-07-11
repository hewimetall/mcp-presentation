"""Minimal IR → LaTeX / Marp sources so builder images have something to compile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NotRequired, TypedDict, cast


class IrSlide(TypedDict):
    title: str
    bullets: NotRequired[list[str]]
    body: NotRequired[str]


class PresentationIr(TypedDict):
    title: str
    author: NotRequired[str]
    slides: NotRequired[list[IrSlide]]


def load_ir(workspace: Path) -> PresentationIr | None:
    path = workspace / "presentation.ir.json"
    if not path.is_file():
        return None
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = "presentation.ir.json must be an object"
        raise ValueError(msg)
    return cast(PresentationIr, raw)


def ensure_latex_source(workspace: Path) -> Path | None:
    """Return existing .tex or generate main.tex from IR. None if nothing to build."""
    for name in ("main.tex", "presentation.tex", "slides.tex"):
        p = workspace / name
        if p.is_file():
            return p
    ir = load_ir(workspace)
    if ir is None:
        return None
    tex = workspace / "main.tex"
    tex.write_text(_ir_to_beamer(ir), encoding="utf-8")
    return tex


def ensure_web_source(workspace: Path) -> Path | None:
    """Return existing web entry or generate slides.md from IR."""
    if (workspace / "package.json").is_file():
        return workspace / "package.json"
    for name in ("slides.md", "presentation.md", "index.md", "deck.md"):
        p = workspace / name
        if p.is_file():
            return p
    ir = load_ir(workspace)
    if ir is None:
        return None
    md = workspace / "slides.md"
    md.write_text(_ir_to_marp(ir), encoding="utf-8")
    return md


def _escape_tex(text: str) -> str:
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = text
    for src, dst in repl.items():
        out = out.replace(src, dst)
    return out


def _ir_to_beamer(ir: PresentationIr) -> str:
    title = _escape_tex(ir.get("title") or "Presentation")
    author = _escape_tex(ir.get("author") or "")
    slides = ir.get("slides") or []
    parts: list[str] = [
        r"\documentclass{beamer}",
        r"\usepackage[T2A]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[russian,english]{babel}",
        rf"\title{{{title}}}",
        rf"\author{{{author}}}",
        r"\begin{document}",
        r"\frame{\titlepage}",
    ]
    for slide in slides:
        st = _escape_tex(slide.get("title") or "")
        parts.append(rf"\begin{{frame}}{{{st}}}")
        bullets = slide.get("bullets") or []
        if bullets:
            parts.append(r"\begin{itemize}")
            for b in bullets:
                parts.append(rf"  \item {_escape_tex(b)}")
            parts.append(r"\end{itemize}")
        body = slide.get("body")
        if body:
            parts.append(_escape_tex(body))
        parts.append(r"\end{frame}")
    if not slides:
        parts.append(r"\begin{frame}{Empty}")
        parts.append(r"No slides in IR.")
        parts.append(r"\end{frame}")
    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def _ir_to_marp(ir: PresentationIr) -> str:
    title = ir.get("title") or "Presentation"
    author = ir.get("author") or ""
    lines = [
        "---",
        "marp: true",
        f"title: {title}",
        f"author: {author}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    if author:
        lines.extend([f"*{author}*", ""])
    for slide in ir.get("slides") or []:
        lines.extend(["---", "", f"## {slide.get('title') or ''}", ""])
        for b in slide.get("bullets") or []:
            lines.append(f"- {b}")
        body = slide.get("body")
        if body:
            lines.extend(["", body, ""])
        lines.append("")
    return "\n".join(lines)
