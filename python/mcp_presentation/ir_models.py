"""Canonical presentation IR — Pydantic models (ADR-0006)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class IrSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)
    body: str | None = None
    notes: str | None = None
    layout: Literal["title", "content", "blank"] | None = None


class PresentationIr(BaseModel):
    """MVP IR subset validated before Docker build."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    title: str = Field(min_length=1)
    author: str | None = None
    theme: str | None = None
    language: str | None = None
    slides: list[IrSlide] = Field(default_factory=list)


def validate_ir_obj(raw: object) -> PresentationIr:
    try:
        return PresentationIr.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid presentation IR: {exc}") from exc


def ir_json_schema() -> dict[str, object]:
    return PresentationIr.model_json_schema()
