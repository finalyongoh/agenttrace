from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

SHA256_HASH_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


class RepositoryInput(BaseModel):
    repository_id: str | None = None
    full_name: str
    github_url: str | None = None
    description: str | None = None
    primary_language: str | None = None
    topics: list[str] = Field(default_factory=list)


class SnapshotInput(BaseModel):
    snapshot_id: str | None = None
    commit_sha: str | None = None
    captured_at: str | None = None
    stars: int | None = None
    forks: int | None = None
    pushed_at: str | None = None


class SourceFile(BaseModel):
    path: str
    content: str
    content_hash: str | None = None

    @model_validator(mode="after")
    def validate_or_default_hash(self) -> SourceFile:
        expected_hash = f"sha256:{hashlib.sha256(self.content.encode('utf-8')).hexdigest()}"
        if not self.content_hash:
            self.content_hash = expected_hash
            return self

        if not SHA256_HASH_PATTERN.fullmatch(self.content_hash):
            raise ValueError("content_hash must use sha256:<64 hex chars> format")

        self.content_hash = self.content_hash.lower()
        if self.content == "":
            return self

        if self.content_hash != expected_hash:
            raise ValueError("content_hash does not match content")

        return self


class ExternalIngestConfig(BaseModel):
    enabled: bool = False
    provider: str = "gitingest"


class AnalysisInputRequest(BaseModel):
    analysis_id: UUID
    repository: RepositoryInput
    snapshot: SnapshotInput | None = None
    readme_text: str | None = None
    file_tree: list[str] = Field(default_factory=list)
    summary_result: dict[str, Any] = Field(default_factory=dict)
    source_files: list[SourceFile] = Field(default_factory=list)
    external_ingest: ExternalIngestConfig = Field(default_factory=ExternalIngestConfig)


class AssembledAnalysisInput(BaseModel):
    request: AnalysisInputRequest
    source_files: list[SourceFile]
    analysis_mode: str
    missing_inputs: list[str] = Field(default_factory=list)
    input_manifest: dict[str, Any] = Field(default_factory=dict)
