"""IR → LaTeX / Marp sources so builder images have something to compile."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_presentation.ir_models import PresentationIr, validate_ir_obj

IR_FILENAME = "presentation.ir.json"


def load_ir(workspace: Path) -> PresentationIr | None:
    path = workspace / IR_FILENAME
    if not path.is_file():
        return None
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return validate_ir_obj(raw)


def write_ir(workspace: Path, ir: PresentationIr) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / IR_FILENAME
    path.write_text(
        ir.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    return path


def ensure_latex_source(workspace: Path) -> Path | None:
    """IR is source of truth when present; else use native .tex. None if nothing."""
    ir = load_ir(workspace)
    if ir is not None:
        tex = workspace / "main.tex"
        tex.write_text(_ir_to_beamer(ir), encoding="utf-8")
        return tex
    for name in ("main.tex", "presentation.tex", "slides.tex"):
        p = workspace / name
        if p.is_file():
            return p
    return None


def ensure_web_source(workspace: Path) -> Path | None:
    """IR is source of truth when present; else package.json / Marp markdown."""
    ir = load_ir(workspace)
    if ir is not None:
        md = workspace / "slides.md"
        md.write_text(_ir_to_marp(ir), encoding="utf-8")
        return md
    if (workspace / "package.json").is_file():
        return workspace / "package.json"
    for name in ("slides.md", "presentation.md", "index.md", "deck.md"):
        p = workspace / name
        if p.is_file():
            return p
    return None


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
    title = _escape_tex(ir.title)
    author = _escape_tex(ir.author or "")
    lang = ir.language or "english"
    babel = "russian,english" if lang.startswith("ru") else "english"
    parts: list[str] = [
        r"\documentclass{beamer}",
        r"\usepackage[T2A]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        rf"\usepackage[{babel}]{{babel}}",
        rf"\title{{{title}}}",
        rf"\author{{{author}}}",
        r"\begin{document}",
        r"\frame{\titlepage}",
    ]
    if ir.theme:
        parts.insert(1, f"% theme hint: {_escape_tex(ir.theme)}")
    for slide in ir.slides:
        st = _escape_tex(slide.title)
        parts.append(rf"\begin{{frame}}{{{st}}}")
        if slide.bullets:
            parts.append(r"\begin{itemize}")
            for b in slide.bullets:
                parts.append(rf"  \item {_escape_tex(b)}")
            parts.append(r"\end{itemize}")
        if slide.body:
            parts.append(_escape_tex(slide.body))
        if slide.notes:
            parts.append(rf"\note{{{_escape_tex(slide.notes)}}}")
        parts.append(r"\end{frame}")
    if not ir.slides:
        parts.append(r"\begin{frame}{Empty}")
        parts.append(r"No slides in IR.")
        parts.append(r"\end{frame}")
    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


def _ir_to_marp(ir: PresentationIr) -> str:
    lines = [
        "---",
        "marp: true",
        f"title: {ir.title}",
    ]
    if ir.author:
        lines.append(f"author: {ir.author}")
    if ir.theme:
        lines.append(f"theme: {ir.theme}")
    lines.extend(["---", "", f"# {ir.title}", ""])
    if ir.author:
        lines.extend([f"*{ir.author}*", ""])
    for slide in ir.slides:
        lines.extend(["---", "", f"## {slide.title}", ""])
        for b in slide.bullets:
            lines.append(f"- {b}")
        if slide.body:
            lines.extend(["", slide.body, ""])
        if slide.notes:
            lines.extend(["", f"<!-- notes: {slide.notes} -->", ""])
        lines.append("")
    return "\n".join(lines)
