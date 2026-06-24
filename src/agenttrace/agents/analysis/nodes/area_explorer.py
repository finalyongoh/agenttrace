"""Area-based exploration node using ReAct agent.

algorithm.md §22.5: 영역 기반 발견 패러다임 — 단일 ReAct 에이전트가 8개 영역을
직접 탐색하며 Finding과 EvidenceRef를 생성한다.
"""
from __future__ import annotations

import time
import os
import hashlib
from pathlib import Path
from typing import Any

from agenttrace.agents.analysis.react_tools import create_react_tools
from agenttrace.agents.analysis.schemas.result import (
    AreaExplorationResult,
    AreaFinding,
    COMMON_ANALYSIS_AREAS,
    EvidenceRef,
    EvidenceSignal,
)
from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.config import get_settings
from agenttrace.logging_config import get_logger
from agenttrace.models import build_openai_analysis_model

logger = get_logger(__name__)


def _build_area_prompt(area_id: str, area_name: str) -> str:
    return f"  - {area_id}: {area_name}"


def _build_system_prompt() -> str:
    areas_text = "\n".join(
        _build_area_prompt(aid, aname) for aid, aname in COMMON_ANALYSIS_AREAS
    )
    return (
        "You are an expert AI software analyst. Your task is to explore a repository "
        "using tools and produce findings for 8 analysis areas.\n\n"
        "ANALYSIS AREAS (you MUST cover ALL of these):\n"
        f"{areas_text}\n\n"
        "EXPLORATION STRATEGY:\n"
        "1. Review the pre-loaded key source files provided in the user message\n"
        "2. The pre-loaded files should be sufficient for ALL 8 areas — analyze them directly\n"
        "3. Use search_code ONLY if a specific area lacks evidence in pre-loaded files\n"
        "4. Use read_file ONLY for files not already pre-loaded\n"
        "5. Produce your structured response as soon as you have enough evidence\n\n"
        "EFFICIENCY RULES:\n"
        "- MINIMIZE tool calls. Start producing findings from pre-loaded files immediately.\n"
        "- Do NOT call get_structure_map — the structure map is already in the user message.\n"
        "- Do NOT read more than 2-3 additional files beyond what's pre-loaded.\n"
        "- Do NOT read test files or documentation unless critical.\n\n"
        "QUALITY RULES (CRITICAL for good output):\n"
        "- For each area, provide at least 2-3 findings with specific details.\n"
        "- Each finding MUST reference specific code: file paths, function names, class names, "
        "or line numbers from the source files.\n"
        "- Do NOT write vague summaries. Instead, describe WHAT the code does and HOW it works.\n"
        "- Example GOOD finding: 'The resolve-library-id tool in packages/mcp/src/index.ts "
        "accepts a library name and returns matched library IDs by querying the Context7 API'\n"
        "- Example BAD finding: 'The project has tools and integrations'\n"
        "- Each AreaFinding summary should be 2-3 sentences describing the key findings for that area.\n"
        "- Include specific function names, class names, API endpoints, or configuration keys "
        "that you found in the source code.\n"
        "- EvidenceRef descriptions should explain what the code at that location does.\n"
        "- For EvidenceRef line_start and line_end: specify the ACTUAL line numbers where the "
        "relevant code is located, NOT always line 1-20. Look at the pre-loaded file contents "
        "and identify the specific lines where each feature is implemented.\n"
        "CRITICAL RULES:\n"
        "- You MUST read actual source code files (.ts, .py, .go, .js, .rs, .java), "
        "NOT just README or .mdx docs.\n"
        "- For each AreaFinding, provide concrete findings with evidence_refs pointing to "
        "EvidenceRef IDs you create.\n"
        "- Each EvidenceRef must have a unique ID (e.g. 'ref-purpose-1', 'ref-exec-2'), "
        "clear path, and description.\n"
        "- If you include line numbers (line_start or line_end), they must be 1-based integers (>= 1). "
        "If line numbers are not available, set them to null.\n"
        "- The status for each AreaFinding must be one of: "
        "'confirmed', 'partially_confirmed', 'unconfirmed', 'not_applicable'.\n"
        "- Each finding's type must be either 'fact' or 'inference'.\n"
        "- agent_type must be one of: 'MCP', 'Skill', 'Eval', 'ToolUse', 'Framework', 'Other', 'Unknown'.\n"
    )


def _select_key_files(state: AnalysisState, max_files: int = 15, max_chars: int = 60000) -> list[tuple[str, str]]:
    """repo_map PageRank 상위 실제 소스 코드 파일들을 선택하여 내용을 읽어온다.

    메타데이터(package.json, .yml, Dockerfile 등)는 최대 3개로 제한하고,
    실제 소스 코드(.ts, .py, .go 등)를 우선 선택한다.
    """
    repo_map = state.get("repo_map", {}) or {}
    definition_ranks = repo_map.get("definition_ranks", {}) or {}
    file_catalog = state.get("file_catalog", []) or []
    catalog_by_path = {item.get("path"): item for item in file_catalog if isinstance(item, dict)}

    source_exts = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java"}
    metadata_exts = {".json", ".yml", ".yaml", ".toml"}
    metadata_names = {"Dockerfile", "docker-compose.yml", ".env.example", "tsconfig.json"}

    file_scores: dict[str, float] = {}
    for key, score in list(definition_ranks.items())[:300]:
        if "::" in key:
            path, _ = key.rsplit("::", 1)
            file_scores[path] = file_scores.get(path, 0.0) + score

    ranked = sorted(file_scores.items(), key=lambda x: -x[1])

    local_repo_dir_str = state.get("local_repo_dir")
    local_repo_dir = Path(local_repo_dir_str) if local_repo_dir_str else None

    source_files: list[tuple[str, str, float]] = []
    metadata_files: list[tuple[str, str, float]] = []

    for path, score in ranked:
        if not local_repo_dir:
            continue
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        name = path.rsplit("/", 1)[-1]
        category = catalog_by_path.get(path, {}).get("category", "")

        is_metadata = ext in metadata_exts or name in metadata_names or name.endswith((".env", ".example"))
        is_source = ext in source_exts or (category == "source" and not is_metadata)

        try:
            full_path = (local_repo_dir / path).resolve()
            if not full_path.is_file() or not full_path.is_relative_to(local_repo_dir.resolve()):
                continue
            content = full_path.read_text(encoding="utf-8", errors="replace")
            if len(content) > 8000:
                content = content[:8000] + "\n... [truncated]"
        except OSError:
            continue

        if is_source:
            source_files.append((path, content, score))
        elif is_metadata:
            metadata_files.append((path, content, score))

    selected: list[tuple[str, str]] = []
    total_chars = 0

    # 1단계: 실제 소스 코드 파일 우선 선택 (최대 max_files - 3개)
    source_limit = max_files - 3
    for path, content, _ in source_files[:source_limit]:
        if total_chars + len(content) > max_chars:
            break
        selected.append((path, content))
        total_chars += len(content)

    # 2단계: 메타데이터 파일 최대 3개 추가 (package.json, Dockerfile 등)
    for path, content, _ in metadata_files[:3]:
        if len(selected) >= max_files:
            break
        if total_chars + len(content) > max_chars:
            break
        selected.append((path, content))
        total_chars += len(content)

    # 3단계: 빈 자리가 있으면 소스 파일 더 추가
    for path, content, _ in source_files[source_limit:]:
        if len(selected) >= max_files:
            break
        if total_chars + len(content) > max_chars:
            break
        selected.append((path, content))
        total_chars += len(content)

    return selected


def _build_user_prompt(state: AnalysisState) -> str:
    readme = (state.get("readme") or "")[:6000]
    repo_map_render = state.get("repo_map_render") or ""
    file_tree = state.get("file_tree") or []
    key_files = _select_key_files(state)

    file_tree_str = ""
    if file_tree:
        paths = []
        for item in file_tree[:80]:
            if isinstance(item, dict):
                paths.append(item.get("path", ""))
            else:
                paths.append(str(item))
        file_tree_str = "\n".join(paths)

    key_files_str = ""
    if key_files:
        parts = []
        for path, content in key_files:
            parts.append(f"=== {path} ===\n{content}")
        key_files_str = "\n\n".join(parts)

    return (
        f"Repository README:\n{readme}\n\n"
        f"Repository File Tree (first 80):\n{file_tree_str}\n\n"
        f"Pre-rendered structure map:\n{repo_map_render[:8000]}\n\n"
        f"Key source files (pre-loaded for your analysis):\n{key_files_str}\n\n"
        "The key source files above are the most important files in this repository, ranked by PageRank.\n"
        "You can use tools (search_code, read_file, list_symbols) to explore additional files if needed,\n"
        "but the pre-loaded files should be sufficient for most of your analysis.\n\n"
        "IMPORTANT: Base your findings on the actual source code provided above. Do NOT just rely on README.\n"
        "1. Review the pre-loaded key files first\n"
        "2. Use search_code only if you need to find something not in the pre-loaded files\n"
        "3. Use read_file only for files NOT already pre-loaded above\n"
        "4. Produce your final findings for all 8 areas\n\n"
        "EFFICIENCY: Minimize tool calls. The pre-loaded files should cover most areas.\n"
        "Produce exactly 8 AreaFinding objects (one per area) and all EvidenceRef objects "
        "they reference. Also determine the agent_type for this repository.\n"
    )


def _build_mock_result(state: AnalysisState) -> dict:
    evidence_refs = _build_fallback_evidence_refs(state)
    agent_type = _infer_fallback_agent_type(state, evidence_refs)
    evidence_ids_by_area = _fallback_evidence_ids_by_area(evidence_refs)
    area_findings = []
    for area_id, area_name in COMMON_ANALYSIS_AREAS:
        refs = evidence_ids_by_area.get(area_id, [])[:3]
        status = "partially_confirmed" if refs else "unconfirmed"
        area_findings.append({
            "area_id": area_id,
            "area_name": area_name,
            "status": status,
            "summary": f"{area_name} 분석은 repo map과 수집된 파일 근거 기준으로 제한적으로 구성되었습니다.",
            "findings": [
                {
                    "content": (
                        f"{area_name}은 {', '.join(refs)} 근거를 기준으로 제한적으로 확인되었습니다."
                        if refs
                        else f"{area_name}은 수집된 파일 근거만으로는 추가 확인이 필요합니다."
                    ),
                    "type": "fact" if refs else "inference",
                    "evidence_refs": refs,
                }
            ],
            "limitations": ["정적 분석은 런타임 동작을 보장하지 않습니다."],
            "unresolved_questions": ["실행 환경에서 동일 흐름이 재현되는지 확인이 필요합니다."],
        })

    evidence_signals = _build_evidence_signals(evidence_refs)
    return {
        "area_findings": area_findings,
        "evidence_refs": evidence_refs,
        "agent_type": agent_type,
        "tech_stack_summary": None,
        "synthesis": {
            "analysis_status": "completed_with_limitations",
            "agent_type": agent_type,
            "tech_stack_summary": _fallback_tech_stack(state),
        },
        "evidence_signals": evidence_signals,
    }


def _build_fallback_evidence_refs(state: AnalysisState) -> list[dict]:
    repo_map = state.get("repo_map", {}) or {}
    files = repo_map.get("files", {}) or {}
    catalog = {
        item.get("path"): item
        for item in state.get("file_catalog", [])
        if isinstance(item, dict) and item.get("path")
    }
    candidate_paths = list(files.keys())
    if not candidate_paths:
        candidate_paths = [
            item.get("path")
            for item in state.get("selected_files", []) or state.get("source_files", [])
            if isinstance(item, dict) and item.get("path")
        ]

    def score(path: str) -> tuple[int, str]:
        lower = path.lower()
        data = files.get(path, {}) or {}
        refs = " ".join([
            path,
            " ".join(data.get("definitions", [])),
            " ".join(data.get("references", [])),
            catalog.get(path, {}).get("category", ""),
        ]).lower()
        val = 0
        
        category = catalog.get(path, {}).get("category") or data.get("category") or ""
        if category == "source":
            val += 200
        elif category == "critical_config":
            val += 50
            
        if lower.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java")):
            val += 50
        if any(token in refs for token in ("mcp", "server", "tool", "agent", "sdk", "client", "api", "search", "context", "resolve")):
            val += 30
        if any(token in lower for token in ("/mcp/", "/server", "src/server", "src/index", "src/main")):
            val += 80
        if any(token in refs for token in ("create", "handler", "route", "resolve-library-id", "tool handler")):
            val += 25
        if lower.endswith(("package.json", "pyproject.toml", ".yml", ".yaml", "dockerfile")):
            val += 20
        if lower.endswith((".md", ".mdx")):
            val += 10
        if "/cli/src/commands/" in lower:
            val -= 40
            
        if "__tests__" in lower or lower.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py")):
            val -= 500
        elif "test" in lower or "example" in lower or "mock" in lower or "fixture" in lower:
            val -= 300
            
        return (-val, path)

    refs: list[dict] = []
    local_repo_dir = Path(state["local_repo_dir"]) if state.get("local_repo_dir") else None
    for idx, path in enumerate(sorted(candidate_paths, key=score)[:12], start=1):
        data = files.get(path, {}) or {}
        category = catalog.get(path, {}).get("category") or data.get("category") or ""
        source_type = _source_type_for_path(path, category)
        excerpt = _read_excerpt(local_repo_dir, path)
        symbols = data.get("definitions", [])[:3]
        refs.append({
            "id": f"fallback-ref-{idx:03d}",
            "source_type": source_type,
            "path": path,
            "symbol": symbols[0] if symbols else None,
            "description": _fallback_description(path, data, category),
            "chunk_id": None,
            "line_start": 1 if excerpt else None,
            "line_end": min(20, len(excerpt.splitlines())) if excerpt else None,
            "content_excerpt": excerpt,
            "content_hash": None,
        })
    return _hydrate_evidence_refs_from_source(local_repo_dir, refs)


def _source_type_for_path(path: str, category: str) -> str:
    lower = path.lower()
    if category == "critical_config" or lower.endswith((".json", ".toml", ".yml", ".yaml", "dockerfile")):
        return "config"
    if lower.endswith((".md", ".mdx", ".txt")):
        return "doc"
    if lower.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java")):
        return "code"
    return "other"


def _read_excerpt(local_repo_dir: Path | None, rel_path: str) -> str | None:
    if not local_repo_dir:
        return None
    try:
        path = (local_repo_dir / rel_path).resolve()
        if not path.is_file() or not path.is_relative_to(local_repo_dir.resolve()):
            return None
        return "\n".join(path.read_text(encoding="utf-8", errors="ignore").splitlines()[:20])
    except Exception:
        return None


def _fallback_description(path: str, data: dict, category: str) -> str:
    symbols = data.get("definitions", [])[:3]
    refs = data.get("references", [])[:5]
    bits = []
    if category:
        bits.append(f"category={category}")
    if symbols:
        bits.append(f"definitions={', '.join(symbols)}")
    if refs:
        bits.append(f"references={', '.join(refs)}")
    return f"{path} ({'; '.join(bits)})" if bits else path


def _fallback_evidence_ids_by_area(evidence_refs: list[dict]) -> dict[str, list[str]]:
    keywords = {
        "project-purpose": ("readme", "package", "docs", "index"),
        "execution-flow": ("server", "entry", "index", "main", "run", "handler", "cli"),
        "architecture-and-modules": ("src/", "packages/", "lib/", "index"),
        "agent-and-llm": ("agent", "mcp", "model", "prompt", "context"),
        "tools-and-integrations": ("tool", "api", "client", "sdk", "redis", "search", "resolve"),
        "state-and-storage": ("redis", "cache", "store", "db", "state"),
        "configuration-and-deployment": ("package.json", ".yml", ".yaml", "docker", "config", "toml"),
        "examples-and-tests": ("test", "example", "readme", "docs/"),
    }
    result: dict[str, list[str]] = {}
    for area_id, terms in keywords.items():
        refs = []
        for ref in evidence_refs:
            haystack = f"{ref.get('path', '')} {ref.get('description', '')}".lower()
            if any(term in haystack for term in terms):
                refs.append(ref["id"])
        refs.sort(key=lambda ref_id: _area_evidence_sort_key(area_id, _ref_by_id(evidence_refs, ref_id)))
        if not refs and evidence_refs:
            refs = [evidence_refs[0]["id"]]
        result[area_id] = refs
    return result


def _ref_by_id(evidence_refs: list[dict], ref_id: str) -> dict:
    for ref in evidence_refs:
        if ref.get("id") == ref_id:
            return ref
    return {}


def _area_evidence_sort_key(area_id: str, ref: dict) -> tuple[int, str]:
    path = (ref.get("path") or "").lower()
    description = (ref.get("description") or "").lower()
    haystack = f"{path} {description}"
    score = 0

    if area_id == "project-purpose":
        if path.endswith(("readme.md", "package.json")) or "docs/" in path:
            score += 80
    elif area_id == "execution-flow":
        if any(token in path for token in ("src/server", "/server", "src/index", "src/main")):
            score += 120
        if any(token in haystack for token in ("create", "handler", "route", "run")):
            score += 40
        if "/cli/src/commands/" in path:
            score -= 50
    elif area_id == "architecture-and-modules":
        if any(token in path for token in ("packages/", "src/", "lib/")):
            score += 80
    elif area_id == "agent-and-llm":
        if any(token in haystack for token in ("agent", "mcp", "model", "prompt", "context")):
            score += 100
    elif area_id == "tools-and-integrations":
        if any(token in haystack for token in ("tool", "api", "client", "sdk", "search", "resolve")):
            score += 100
    elif area_id == "state-and-storage":
        if any(token in haystack for token in ("redis", "cache", "store", "db", "state")):
            score += 100
    elif area_id == "configuration-and-deployment":
        if path.endswith(("package.json", "pyproject.toml", ".yml", ".yaml", "dockerfile")):
            score += 100
    elif area_id == "examples-and-tests":
        if any(token in path for token in ("test", "example", "docs/", "readme")):
            score += 100

    return (-score, path)


def _infer_fallback_agent_type(state: AnalysisState, evidence_refs: list[dict]) -> str:
    text = " ".join([
        state.get("readme", ""),
        str(state.get("metadata", {})),
        " ".join(ref.get("path", "") for ref in evidence_refs),
        " ".join(ref.get("description", "") for ref in evidence_refs),
    ]).lower()
    if "mcp" in text or "modelcontextprotocol" in text:
        return "MCP"
    if "skill" in text:
        return "Skill"
    if "eval" in text or "benchmark" in text:
        return "Eval"
    if "agent" in text:
        return "Framework"
    if "tool" in text or "api" in text:
        return "ToolUse"
    return "Unknown"


def _fallback_tech_stack(state: AnalysisState) -> dict:
    metadata = state.get("metadata", {}) or {}
    language = metadata.get("primary_language") or "Unknown"
    topics = metadata.get("topics") or []
    return {
        "primary_language": language,
        "frameworks": [topic for topic in topics if topic in {"langchain", "mcp", "sdk"}],
        "dependencies": [],
    }


def _build_evidence_signals(evidence_refs: list[dict]) -> list[dict]:
    signals = []
    for idx, ref in enumerate(evidence_refs, start=1):
        path = ref.get("path") or "unknown"
        signals.append({
            "signal_id": f"signal-{idx:04d}",
            "signal_type": _infer_signal_type(path),
            "path": path,
            "chunk_id": ref.get("chunk_id") or "",
            "line_start": ref.get("line_start"),
            "line_end": ref.get("line_end"),
            "content_excerpt": ref.get("content_excerpt") or "",
            "content_hash": ref.get("content_hash") or "",
            "summary": ref.get("description") or "",
            "confidence": 0.6,
        })
    return signals


def _invoke_agent_with_retry(agent, messages, *, config, log, max_retries=3):
    for attempt in range(max_retries):
        try:
            return agent.invoke(messages, config=config)
        except Exception as exc:
            exc_str = str(exc).lower()
            if ("rate_limit" in exc_str or "429" in exc_str) and attempt < max_retries - 1:
                wait_time = 20 * (attempt + 1)
                log.warning(
                    f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}/{max_retries}",
                    error=str(exc)[:300],
                )
                time.sleep(wait_time)
                continue
            raise
    raise RuntimeError("Max retries exceeded")


def _invoke_structured_with_retry(fn, prompt_value, *, log, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fn(prompt_value)
        except Exception as exc:
            exc_str = str(exc).lower()
            if ("rate_limit" in exc_str or "429" in exc_str) and attempt < max_retries - 1:
                wait_time = 20 * (attempt + 1)
                log.warning(
                    f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}/{max_retries}",
                    error=str(exc)[:300],
                )
                time.sleep(wait_time)
                continue
            raise
    raise RuntimeError("Max retries exceeded")


def area_explorer(state: AnalysisState) -> AnalysisState:
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    log = logger.bind(node="area_explorer", run_id=run_id)
    log.info("시작")

    settings = get_settings()
    if os.getenv("AGENTTRACE_SKIP_AREA_AGENT") in {"1", "true", "TRUE", "yes"}:
        log.warning("AGENTTRACE_SKIP_AREA_AGENT 설정됨, fallback 결과 반환")
        result = _build_mock_result(state)
        log.info(
            "완료(fallback)",
            area_findings=len(result["area_findings"]),
            evidence_refs=len(result["evidence_refs"]),
            duration_ms=int((time.perf_counter() - _t) * 1000),
        )
        return result

    if not settings.openai_api_key:
        log.warning("OPENAI_API_KEY 없음, mock 결과 반환")
        result = _build_mock_result(state)
        log.info(
            "완료(mock)",
            area_findings=len(result["area_findings"]),
            duration_ms=int((time.perf_counter() - _t) * 1000),
        )
        return result

    local_repo_dir_str = state.get("local_repo_dir")
    local_repo_dir = Path(local_repo_dir_str) if local_repo_dir_str else None
    repo_map = state.get("repo_map", {}) or {}
    file_catalog = state.get("file_catalog", []) or []

    try:
        model = build_openai_analysis_model()
        key_files = _select_key_files(state)

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(state)

        if len(key_files) >= 5:
            log.info("단일 structured output 호출 (key_files=%d)", len(key_files))
            structured_model = model.with_structured_output(AreaExplorationResult)

            from langchain_core.prompts import ChatPromptTemplate
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{content}"),
            ])
            prompt_value = prompt.invoke({"content": user_prompt})

            structured_response = _invoke_structured_with_retry(
                structured_model.invoke,
                prompt_value,
                log=log,
            )
        else:
            log.info("ReAct 에이전트 호출 (key_files=%d, 부족하여 도구 탐색 필요)", len(key_files))
            from langchain.agents import create_agent

            tools = create_react_tools(local_repo_dir, repo_map, file_catalog)
            agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
                response_format=AreaExplorationResult,
            )

            result = _invoke_agent_with_retry(
                agent,
                {"messages": [{"role": "user", "content": user_prompt}]},
                config={"recursion_limit": 40},
                log=log,
            )

            structured_response = result.get("structured_response")
            if structured_response is None:
                messages = result.get("messages", [])
                last_msg_type = type(messages[-1]).__name__ if messages else "none"
                last_msg_content = ""
                if messages:
                    last = messages[-1]
                    content = getattr(last, "content", None) or (last.get("content") if isinstance(last, dict) else "")
                    last_msg_content = str(content)[:500] if content else ""
                log.warning(
                    "structured_response 없음, mock fallback",
                    last_msg_type=last_msg_type,
                    last_msg_content=last_msg_content,
                    message_count=len(messages),
                )
                mock = _build_mock_result(state)
                log.info(
                    "완료(mock-fallback)",
                    area_findings=len(mock["area_findings"]),
                    duration_ms=int((time.perf_counter() - _t) * 1000),
                )
                return mock

        area_findings = [af.model_dump() for af in structured_response.area_findings]
        evidence_refs = [
            _sanitize_ref(er.model_dump()) if hasattr(er, "model_dump") else _sanitize_ref(er)
            for er in structured_response.evidence_refs
        ]
        evidence_refs = _hydrate_evidence_refs_from_source(local_repo_dir, evidence_refs)
        agent_type = structured_response.agent_type or "Unknown"
        tech_stack = None
        if structured_response.tech_stack_summary:
            tech_stack = structured_response.tech_stack_summary
            if hasattr(tech_stack, "model_dump"):
                tech_stack = tech_stack.model_dump()

        evidence_ids = {ref.get("id") for ref in evidence_refs}
        for af in area_findings:
            for finding in af.get("findings", []):
                finding["evidence_refs"] = [
                    rid for rid in finding.get("evidence_refs", []) if rid in evidence_ids
                ]

        all_area_ids = {aid for aid, _ in COMMON_ANALYSIS_AREAS}
        present_area_ids = {af.get("area_id") for af in area_findings}
        for area_id, area_name in COMMON_ANALYSIS_AREAS:
            if area_id not in present_area_ids:
                area_findings.append({
                    "area_id": area_id,
                    "area_name": area_name,
                    "status": "unconfirmed",
                    "summary": "분석 중 누락됨",
                    "findings": [],
                    "limitations": ["area_explorer 출력 누락"],
                    "unresolved_questions": [],
                })

        evidence_signals: list[dict] = []
        for idx, ref in enumerate(evidence_refs, start=1):
            path = ref.get("path") or "unknown"
            sig_type = _infer_signal_type(path)
            evidence_signals.append({
                "signal_id": f"signal-{idx:04d}",
                "signal_type": sig_type,
                "path": path,
                "chunk_id": ref.get("chunk_id") or "",
                "line_start": ref.get("line_start"),
                "line_end": ref.get("line_end"),
                "content_excerpt": ref.get("content_excerpt") or "",
                "content_hash": ref.get("content_hash") or "",
                "summary": ref.get("description") or "",
                "confidence": 0.8,
            })

        significant_areas = sum(
            1 for af in area_findings
            if af.get("status") == "confirmed"
        )
        analysis_status = "completed" if significant_areas >= 5 else "completed_with_limitations"

        log.info(
            "완료",
            area_findings=len(area_findings),
            evidence_refs=len(evidence_refs),
            agent_type=agent_type,
            duration_ms=int((time.perf_counter() - _t) * 1000),
        )

        return {
            "area_findings": area_findings,
            "evidence_refs": evidence_refs,
            "agent_type": agent_type,
            "tech_stack_summary": tech_stack,
            "evidence_signals": evidence_signals,
            "synthesis": {
                "analysis_status": analysis_status,
                "agent_type": agent_type,
                "tech_stack_summary": tech_stack or {"ko": "미확인", "en": "Unknown"},
            },
        }

    except Exception as exc:
        import traceback
        log.error(
            f"area_explorer failed, falling back to mock: {exc}",
            traceback=traceback.format_exc()[:2000],
        )
        result = _build_mock_result(state)
        log.info(
            "완료(mock-error)",
            area_findings=len(result["area_findings"]),
            duration_ms=int((time.perf_counter() - _t) * 1000),
        )
        return result


def _sanitize_ref(ref: dict) -> dict:
    for field in ["line_start", "line_end"]:
        val = ref.get(field)
        if val is not None and (not isinstance(val, int) or val < 1):
            ref[field] = None
    start = ref.get("line_start")
    end = ref.get("line_end")
    if start is not None and end is not None and start > end:
        ref["line_start"] = end
        ref["line_end"] = start
    return ref


def _hydrate_evidence_refs_from_source(
    local_repo_dir: Path | None,
    evidence_refs: list[dict],
) -> list[dict]:
    if not local_repo_dir:
        return evidence_refs

    base_dir = local_repo_dir.resolve()
    hydrated: list[dict] = []
    for ref in evidence_refs:
        next_ref = dict(ref)
        path_value = next_ref.get("path")
        if not path_value or path_value == "unknown":
            hydrated.append(next_ref)
            continue

        try:
            source_path = (base_dir / str(path_value)).resolve()
            if not source_path.is_relative_to(base_dir) or not source_path.is_file():
                hydrated.append(next_ref)
                continue

            content = source_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            if not lines:
                hydrated.append(next_ref)
                continue

            if not next_ref.get("content_hash"):
                next_ref["content_hash"] = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

            start = next_ref.get("line_start")
            end = next_ref.get("line_end")
            if not isinstance(start, int) or start < 1:
                start = 1
            if start > len(lines):
                start = 1
            if not isinstance(end, int) or end < start:
                end = min(len(lines), start + 19)
            end = min(end, len(lines))

            if not next_ref.get("content_excerpt"):
                next_ref["content_excerpt"] = "\n".join(lines[start - 1:end])
            next_ref["line_start"] = start
            next_ref["line_end"] = end
        except OSError:
            pass
        hydrated.append(next_ref)

    return hydrated


def _infer_signal_type(file_path: str) -> str:
    lower_path = file_path.lower()
    if lower_path.endswith((".md", ".mdx", ".txt")):
        return "DOCUMENTATION_CORROBORATION"
    if lower_path.endswith((".yml", ".yaml", ".json", ".toml", "dockerfile")) or "docker-compose" in lower_path:
        return "CONFIGURATION_EVIDENCE"
    if lower_path.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".sh", ".rs", ".java", ".c", ".cpp", ".h")):
        return "IMPLEMENTATION_EVIDENCE"
    return "METADATA_SIGNAL"
