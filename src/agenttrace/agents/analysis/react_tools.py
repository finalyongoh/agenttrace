"""ReAct 에이전트용 코드 탐색 도구.

algorithm.md §22.5: Repository Map으로 후보를 찾은 후 원문 청크를 다시 수집한다.
LLM이 구조 지도를 보고 능동적으로 파일을 요청하는 ReAct 패턴을 구현한다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


def create_react_tools(
    local_repo_dir: Path | None,
    repo_map: dict[str, Any],
    file_catalog: list[dict],
) -> list[Any]:
    """evidence_evaluator ReAct 에이전트에 바인딩할 도구들을 생성한다.

    도구:
        read_file(path) — 파일 전체 내용을 읽어온다
        search_code(query) — 코드베이스에서 문자열 검색
        list_symbols(file_path) — 특정 파일의 정의/참조 심볼 목록
        get_structure_map() — 전체 구조 지도 (파일 경로 + 상위 심볼)
    """

    _file_cache: dict[str, str] = {}
    _file_catalog_paths = [e.get("path", "") for e in file_catalog if e.get("path")]

    @tool
    def read_file(file_path: str) -> str:
        """Read the full content of a source file from the repository.

        Args:
            file_path: Relative path of the file (e.g., "src/agent.ts")

        Returns:
            Full file content as text, or error message if file not found.
        """
        if not file_path:
            return "Error: file_path is required."

        # 캐시 확인
        if file_path in _file_cache:
            return _file_cache[file_path]

        # 로컬 디스크에서 읽기
        if local_repo_dir:
            try:
                resolved_base = local_repo_dir.resolve()
                resolved_target = (local_repo_dir / file_path).resolve()
                if not resolved_target.is_relative_to(resolved_base):
                    return f"Error: path traversal detected for {file_path}"
                full_path = local_repo_dir / file_path
                if full_path.exists():
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    # 파일이 너무 크면 앞부분만 (컨텍스트 폭발 방지)
                    if len(content) > 20000:
                        content = content[:20000] + "\n\n... [truncated, file too large]"
                    _file_cache[file_path] = content
                    return content
                return f"File not found: {file_path}"
            except Exception as exc:
                return f"Error reading {file_path}: {exc}"

        return f"Error: local_repo_dir not available, cannot read {file_path}"

    @tool
    def search_code(query: str) -> str:
        """Search for a string or pattern across all repository source files.

        Returns matching lines with file paths and line numbers.
        Use this to find where a function, class, or keyword is used.

        Args:
            query: String to search for (case-insensitive)

        Returns:
            Matching lines with file:line format, up to 50 results.
        """
        if not query or not local_repo_dir:
            return "No results: query or local_repo_dir is empty."

        query_lower = query.lower()
        # 최대 30개 결과로 제한 (컨텍스트 폭발 방지)
        results: list[str] = []
        files_data = repo_map.get("files", {})

        for file_path_str, file_data in files_data.items():
            if len(results) >= 30:
                break
            # 심볼 매칭으로 빠른 검색
            definitions = file_data.get("definitions", [])
            references = file_data.get("references", [])
            all_symbols = definitions + references
            matching_symbols = [s for s in all_symbols if query_lower in s.lower()]

            if matching_symbols:
                # 실제 파일에서 라인 검색
                try:
                    full_path = local_repo_dir / file_path_str
                    if full_path.exists():
                        for line_no, line in enumerate(
                            full_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                        ):
                            if query_lower in line.lower():
                                results.append(f"{file_path_str}:{line_no}: {line.strip()[:120]}")
                                if len(results) >= 50:
                                    break
                except Exception:
                    pass

        if not results:
            return f"No matches found for '{query}'."
        return "\n".join(results)

    @tool
    def list_symbols(file_path: str) -> str:
        """List all defined symbols (classes, functions, constants) in a file.

        Use this to understand what a file contains before reading its full content.

        Args:
            file_path: Relative path of the file

        Returns:
            List of symbol names with their kinds, or 'not found' message.
        """
        files_data = repo_map.get("files", {})
        file_data = files_data.get(file_path)
        if not file_data:
            # 대소문자 무시 매칭
            for fp, fd in files_data.items():
                if fp.lower() == file_path.lower():
                    file_data = fd
                    break

        if not file_data:
            return f"File not in repo map: {file_path}"

        definitions = file_data.get("definitions", [])
        references = file_data.get("references", [])
        category = file_data.get("category", "unknown")

        lines = [f"File: {file_path} (category: {category})"]
        if definitions:
            lines.append(f"Definitions ({len(definitions)}):")
            for d in definitions[:50]:
                lines.append(f"  - {d}")
        if references:
            lines.append(f"References ({len(references)}):")
            for r in references[:30]:
                lines.append(f"  - {r}")
        return "\n".join(lines)

    @tool
    def get_structure_map() -> str:
        """Get the repository structure map showing all files and their key symbols.

        This is the starting point for exploration. Review this map first,
        then use read_file to get full content of files that seem relevant.

        Returns:
            Structured map: file paths with their top definitions, sorted by PageRank importance.
        """
        definition_ranks = repo_map.get("definition_ranks", {})
        files_data = repo_map.get("files", {})

        # 상위 정의를 파일별로 그룹화
        file_symbols: dict[str, list[str]] = {}
        for key, score in list(definition_ranks.items())[:200]:
            if "::" in key:
                path, symbol = key.rsplit("::", 1)
                if path not in file_symbols:
                    file_symbols[path] = []
                file_symbols[path].append(symbol)

        # critical_config 파일 추가
        for path, data in files_data.items():
            if data.get("category") == "critical_config" and path not in file_symbols:
                file_symbols[path] = []

        lines = ["=== Repository Structure Map ==="]
        lines.append(f"Total files: {len(files_data)}")
        lines.append("")

        for path in sorted(file_symbols.keys()):
            symbols = file_symbols[path]
            category = files_data.get(path, {}).get("category", "")
            if symbols:
                lines.append(f"{path} [{category}]")
                for s in symbols[:10]:
                    lines.append(f"  - {s}")
            else:
                lines.append(f"{path} [{category}] (no ranked symbols)")
            lines.append("")

        return "\n".join(lines)

    return [read_file, search_code, list_symbols, get_structure_map]
