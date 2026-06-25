from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SymbolTag(BaseModel):
    file_path: str
    symbol_name: str
    symbol_kind: str
    line_start: int
    line_end: int | None = None
    tag_kind: Literal["definition", "reference"]


class SymbolEdge(BaseModel):
    source_file: str
    target_file: str
    symbol_name: str
    reference_count: int
    weight: float


class FileRank(BaseModel):
    file_path: str
    pagerank_score: float
    personalization_reasons: list[str] = Field(default_factory=list)


class DefinitionRank(BaseModel):
    file_path: str
    symbol_name: str
    score: float
    supporting_edges: list[str] = Field(default_factory=list)


class RepoMapEntry(BaseModel):
    file_path: str
    selected_symbols: list[str]
    rendered_context: str | None = None
    selection_reason: list[str] = Field(default_factory=list)
