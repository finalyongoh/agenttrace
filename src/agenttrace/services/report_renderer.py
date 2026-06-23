from __future__ import annotations

from typing import Any


def render_markdown_report(report_sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for section in sorted(report_sections, key=lambda item: item.get("section_id", 0)):
        title = _normalize_title(section.get("title") or section.get("section_name") or "Untitled")
        body = (section.get("body_markdown") or "").strip()
        parts.append(f"# {title}\n\n{body}".rstrip())
        diagram = (section.get("mermaid_diagram") or "").strip()
        if diagram:
            parts.append(f"```mermaid\n{diagram}\n```")
    return "\n\n".join(parts).rstrip() + "\n"


def _normalize_title(title: str) -> str:
    stripped = title.strip()
    while stripped.startswith("#"):
        stripped = stripped[1:].lstrip()
    return stripped
