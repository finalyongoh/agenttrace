from __future__ import annotations

import re

MAX_LINE_LENGTH = 100
MAX_TOKENS_DEFAULT = 1024


def _count_tokens(text: str) -> int:
    """토큰 수 추정. algorithm.md §14: 긴 경우 샘플링."""
    char_count = len(text)
    if char_count < 10000:
        return char_count // 4
    sample = text[:10000]
    sample_tokens = len(sample) // 4
    return int(sample_tokens * char_count / len(sample))


def _truncate_line(line: str) -> str:
    """algorithm.md §13.6: 각 라인 최대 100자."""
    return line[:MAX_LINE_LENGTH]


def render_repo_map(
    definition_ranks: dict[str, float],
    symbol_tags: list[dict] | None = None,
    max_tokens: int = MAX_TOKENS_DEFAULT,
    special_files: list[str] | None = None,
) -> str:
    """토큰 예산에 맞춘 Repository Map 렌더링.

    algorithm.md §13: 이진 탐색 + 코드 구조 렌더링.
    """
    special_files = special_files or []
    entries = list(definition_ranks.items())

    if not entries and not special_files:
        return ""

    # special_files를 맨 앞에 배치
    header_lines = []
    for sf in special_files:
        header_lines.append(sf)

    # definition_ranks 상위부터 렌더링
    def _render_subset(count: int) -> str:
        lines = list(header_lines)
        for key, _score in entries[:count]:
            # key 형식: "file_path::symbol_name"
            if "::" in key:
                file_path, symbol = key.rsplit("::", 1)
                lines.append(f"{file_path}")
                lines.append(f"  {symbol}")
            else:
                lines.append(key)
        rendered = "\n".join(lines)
        # 각 라인 100자 truncation
        rendered = "\n".join(_truncate_line(line) for line in rendered.splitlines())
        return rendered

    # 이진 탐색으로 max_tokens 맞춤 (§13.2)
    low = 0
    high = len(entries)
    best = ""

    # 초기 추정값 (§13.2: max_tokens / 25)
    initial = max(1, max_tokens // 25)
    mid = min(initial, high)
    rendered = _render_subset(mid)
    if _count_tokens(rendered) <= max_tokens:
        best = rendered
        low = mid
    else:
        high = mid

    while low <= high:
        mid = (low + high) // 2
        rendered = _render_subset(mid)
        tokens = _count_tokens(rendered)
        if tokens <= max_tokens:
            best = rendered
            low = mid + 1
        else:
            high = mid - 1

    return best
