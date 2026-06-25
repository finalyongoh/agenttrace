from __future__ import annotations

import hashlib
import os
import pickle
import re
from pathlib import Path

from agenttrace.agents.analysis.schemas.repo_map import SymbolTag

try:
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tsts
    import tree_sitter_javascript as tsjs
    import tree_sitter_go as tsgo
    from tree_sitter import Language, Parser, Query, QueryCursor

    LANGUAGE_MAP = {
        ".py": Language(tspython.language()),
        ".ts": Language(tsts.language_typescript()),
        ".tsx": Language(tsts.language_tsx()),
        ".js": Language(tsjs.language()),
        ".jsx": Language(tsjs.language()),
        ".go": Language(tsgo.language()),
    }
except Exception:
    LANGUAGE_MAP = {}
    Language = None
    Parser = None
    Query = None
    QueryCursor = None

QUERY_DIR = Path(__file__).parent / "queries"
CACHE_DIR = Path(".agenttrace.tags.cache")

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_DEF_PATTERNS = [
    re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)"),
]

_QUERY_CACHE: dict[str, str] = {}
_mtime_cache: dict[str, tuple[float, list[SymbolTag]]] = {}


def _content_hash(content: str) -> float:
    """content 기반 캐시 키 (mtime 대용)."""
    return float(int(hashlib.sha256(content.encode("utf-8")).hexdigest()[:16], 16))


def _load_cache(path: str, content_hash: float) -> list[SymbolTag] | None:
    """algorithm.md §6: content hash 기반 파일별 캐시."""
    cached = _mtime_cache.get(path)
    if cached and cached[0] == content_hash:
        return cached[1]
    return None


def _save_cache(path: str, content_hash: float, tags: list[SymbolTag]) -> None:
    """캐시 저장 (인메모리)."""
    _mtime_cache[path] = (content_hash, tags)


_EXT_TO_QUERY_NAME = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
}


def _load_query(ext: str) -> str:
    if ext not in _QUERY_CACHE:
        query_name = _EXT_TO_QUERY_NAME.get(ext, ext[1:])
        query_path = QUERY_DIR / f"{query_name}-tags.scm"
        _QUERY_CACHE[ext] = query_path.read_text()
    return _QUERY_CACHE[ext]


def extract_symbols_tree_sitter(path: str, content: str) -> list[SymbolTag]:
    """Tree-sitter AST에서 정의/참조 태그 추출.

    algorithm.md §5.2. 미지원 언어는 regex fallback 사용.
    §6: content hash 기반 인메모리 캐시 적용.
    """
    # 캐시 확인
    ch = _content_hash(content)
    cached = _load_cache(path, ch)
    if cached is not None:
        return cached

    ext = Path(path).suffix
    language = LANGUAGE_MAP.get(ext)

    if language is None or Parser is None:
        result = _fallback_regex_extract(path, content)
        _save_cache(path, ch, result)
        return result

    try:
        parser = Parser(language)
        tree = parser.parse(content.encode("utf-8"))
        query_text = _load_query(ext)
        query = Query(language, query_text)
        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)

        tags: list[SymbolTag] = []
        for capture_name, nodes in captures.items():
            kind = "definition" if "definition" in capture_name else "reference"
            symbol_kind = capture_name.split(".")[-1]
            for node in nodes:
                name = node.text.decode("utf-8", errors="replace")
                tags.append(SymbolTag(
                    file_path=path,
                    symbol_name=name,
                    symbol_kind=symbol_kind,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1 if node.end_point[0] != node.start_point[0] else None,
                    tag_kind=kind,
                ))

        if not any(t.tag_kind == "reference" for t in tags):
            pygments_refs = _pygments_fallback_references(path, content)
            for ref_name in pygments_refs:
                if not any(t.symbol_name == ref_name and t.tag_kind == "reference" for t in tags):
                    tags.append(SymbolTag(
                        file_path=path,
                        symbol_name=ref_name,
                        symbol_kind="identifier",
                        line_start=0,
                        tag_kind="reference",
                    ))

        _save_cache(path, ch, tags)
        return tags
    except Exception:
        result = _fallback_regex_extract(path, content)
        _save_cache(path, ch, result)
        return result


def _fallback_regex_extract(path: str, content: str) -> list[SymbolTag]:
    """Tree-sitter 미지원 언어용 regex 기반 심볼 추출."""
    definitions: set[str] = set()
    for pattern in _DEF_PATTERNS:
        definitions.update(pattern.findall(content))
    references = set(_IDENT_RE.findall(content)) - definitions

    tags: list[SymbolTag] = []
    for name in sorted(definitions):
        tags.append(SymbolTag(
            file_path=path,
            symbol_name=name,
            symbol_kind="definition",
            line_start=0,
            tag_kind="definition",
        ))
    for name in sorted(references):
        tags.append(SymbolTag(
            file_path=path,
            symbol_name=name,
            symbol_kind="identifier",
            line_start=0,
            tag_kind="reference",
        ))
    return tags


def _pygments_fallback_references(path: str, content: str) -> list[str]:
    """Tree-sitter 참조 추출이 빈 경우 Pygments Token.Name 보완. §5.4."""
    try:
        from pygments import lex
        from pygments.lexers import get_lexer_for_filename
        from pygments.token import Token
    except Exception:
        return []

    try:
        lexer = get_lexer_for_filename(path)
    except Exception:
        return []

    refs: set[str] = set()
    for token_type, value in lex(content, lexer):
        if token_type in (Token.Name, Token.Name.Function, Token.Name.Class):
            if len(value) >= 3:
                refs.add(value)
    return sorted(refs)
