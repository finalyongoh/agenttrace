from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def compute_content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class SourceRecord:
    path: str
    content: str
    content_hash: str

    @property
    def lines(self) -> list[str]:
        return self.content.splitlines()


class SourceInventory:
    def __init__(self, records: dict[str, SourceRecord]):
        self.records = records

    @classmethod
    def from_source_files(cls, source_files: list[dict[str, Any]]) -> "SourceInventory":
        records: dict[str, SourceRecord] = {}
        for source in source_files:
            path = str(source.get("path") or source.get("file_path") or "")
            content = str(source.get("content") or "")
            if not path or content == "":
                continue
            content_hash = str(source.get("content_hash") or compute_content_hash(content))
            records[path] = SourceRecord(path=path, content=content, content_hash=content_hash)
        return cls(records)

    @classmethod
    def from_directory(cls, base_dir: Path, paths: list[str]) -> "SourceInventory":
        records: dict[str, SourceRecord] = {}
        resolved_base = base_dir.resolve()
        for rel_path in paths:
            try:
                file_path = (resolved_base / rel_path).resolve()
                if not file_path.is_relative_to(resolved_base) or not file_path.is_file():
                    continue
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            records[rel_path] = SourceRecord(
                path=rel_path,
                content=content,
                content_hash=compute_content_hash(content),
            )
        return cls(records)

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "SourceInventory":
        inventory = cls.from_source_files(state.get("source_files") or [])
        if inventory.records:
            return inventory

        local_repo_dir = state.get("local_repo_dir")
        if not local_repo_dir:
            return cls({})

        candidate_paths = [
            str(item.get("path"))
            for item in state.get("file_catalog", []) or state.get("file_tree", [])
            if isinstance(item, dict) and item.get("path")
        ]
        if not candidate_paths:
            candidate_paths = [
                str(ref.get("path"))
                for ref in state.get("final_result", {}).get("evidence_refs", [])
                if isinstance(ref, dict) and ref.get("path")
            ]
        return cls.from_directory(Path(local_repo_dir), candidate_paths)

    def excerpt(self, path: str, line_start: int, line_end: int) -> str:
        record = self.records[path]
        lines = record.lines
        start = max(1, line_start)
        end = min(max(start, line_end), len(lines))
        return "\n".join(lines[start - 1:end])

    def build_evidence_ref(
        self,
        *,
        ref_id: str,
        path: str,
        line_start: int,
        line_end: int,
        source_type: str,
        description: str,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        record = self.records[path]
        return {
            "id": ref_id,
            "source_type": source_type,
            "path": path,
            "symbol": symbol,
            "description": description,
            "chunk_id": None,
            "line_start": line_start,
            "line_end": line_end,
            "content_excerpt": self.excerpt(path, line_start, line_end),
            "content_hash": record.content_hash,
        }

    def validate_evidence_ref(self, ref: dict[str, Any]) -> list[str]:
        path = str(ref.get("path") or "")
        if path not in self.records:
            return [f"source path not found: {path}"]

        record = self.records[path]
        errors: list[str] = []
        if ref.get("content_hash") != record.content_hash:
            errors.append(f"content hash mismatch: {path}")

        start = ref.get("line_start")
        end = ref.get("line_end")
        if not isinstance(start, int) or not isinstance(end, int):
            errors.append(f"line range missing: {path}")
            return errors

        if start < 1 or end < start or end > len(record.lines):
            errors.append(f"line range invalid: {path}")
            return errors

        expected_excerpt = self.excerpt(path, start, end)
        if (ref.get("content_excerpt") or "") != expected_excerpt:
            errors.append(f"excerpt mismatch: {path}:{start}-{end}")
        return errors
