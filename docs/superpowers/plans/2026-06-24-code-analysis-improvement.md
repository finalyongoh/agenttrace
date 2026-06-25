# Code Analysis Improvement Plan — algorithm.md 기반 Repo Map 고도화

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 각 Task는 `agy -p` CLI 디스패치 단위로 세분화됨.

**Goal:** `docs/algorithm.md`가 권장하는 Aider Repository Map 알고리즘 16개 항목을 현재 코드분석 파이프라인에 적용. 정확한 심볼 추출, 구조적 그래프 가중치, Personalized PageRank, BM25+임베딩 하이브리드 검색, 토큰 예산 렌더링을 도입.

**Architecture:** Tree-sitter 기반 심볼 추출 → 가중치 그래프 → Personalized PageRank → 정의 단위 랭킹 → BM25/임베딩/PageRank 혼합 청크 검색. MAX_FILES=300 제거로 전체 리포지토리 정보 보존.

**Tech Stack:** Python, LangGraph node functions, pytest, tree-sitter (7 languages), rank-bm25, pygments, pgvector.

**Reference:** `docs/algorithm.md` §5-22, AGENTS.md §5 (Subagent-Driven Development)

---

## 사용자 결정사항

- **범위:** 전체 16개 항목 (BM25/임베딩 연동 포함)
- **파일 수집:** 전체 트리 유지 + 지연 fetch (MAX_FILES=300 제거)
- **area_id 주입:** claim별 영역 매핑 자동 추론

---

## 모델 Tier 매핑 (AGENTS.md §5-3)

| Tier | agy 모델 | 적용 기준 |
|---|---|---|
| **Flash** | `Gemini 3.5 Flash (Low)` 또는 `(Medium)` | 단일 함수 추가·삭제, import 교체, 단순 블록 제거, 직관적 단위 테스트 |
| **Standard** | `Claude Sonnet 4.6 (Thinking)` | 기존 코드 흐름 이해 필요, 리팩토링, 테스트 rewrite |
| **Full** | `Claude Opus 4.6 (Thinking)` | Spec compliance 검토, 설계 판정, 통합 검증 |

---

## 디스패치 순서 요약

```
Round 1  (병렬 3): 1A || 1B || 1C
Round 2  (순차):   2A-1 → 2A-2 → 2A-3
Round 3  (병렬 2): 2B-1 || 2C
Round 4  (순차):   2B-2 → 2B-3 → 2D
Round 5  (순차):   3A → 3B-1 → 3B-2 → 3B-3
Round 6  (순차):   3C-1 → 3C-2 → 3D
Round 7  (순차):   4A-1 → 4A-2 → 4A-3 → 4B → 4C-1 → 4C-2 → 4C-3
Round 8  (순차):   4D-1 → 4D-2 → 4D-3 → 4D-4 → 4E
Round 9  (병렬 2): 5A-1 || 5B-1
Round 10 (병렬 2): 5A-2 || 5B-2
Round 11 (병렬 2): 5A-3 || 5B-3
Round 12 (병렬 2): 6A-1 || 6B-1
Round 13 (병렬 2): 6A-2 || 6B-2
Round 14 (순차):   6C-1 → 6C-2 → 6C-3 → 6C-4
Round 15 (병렬 3): 7A-1 || 7B-1 || 7C-1
Round 16 (병렬 3): 7A-2 || 7B-2 || 7C-2
Round 17 (병렬 3): 7A-3 || 7B-3
Round 18 (순차):   8A → 8B → 8C → 8D
```

**총 48 Task, 18 Round.** 병렬 디스패치로 실제 wall time은 순차 ~30 Task 분량.

---

## agy 프롬프트 작성 가이드라인 (AGENTS.md §5-2)

각 Task의 agy 프롬프트는 다음을 포함해야 함:

```
[대상 파일 + 정확한 위치]
[추가/교체/삭제할 코드 블록 (diff 수준)]
[테스트 assert 조건 (함수 반환값, call_count 등 구체적)]
[검증 명령어: rtk .venv/bin/pytest <경로> -q]
```

**금지 사항 (§5-4):**
- Task 하나에 구현 + 테스트 rewrite 동시 포함 금지
- 서브에이전트에게 plan 파일 직접 읽기 금지 (full text 전달)
- 같은 파일 수정 Task 병렬 실행 금지 (§5-5 파일 비중복)

---

## Phase 1: 기반 데이터 모델 (병렬 실행: 1A || 1B || 1C)

### Task 1A: AnalysisState 필드 확장

- [ ] **Step 1: state.py 필드 추가**

**파일:** `src/agenttrace/agents/analysis/state.py`
**위치:** L55 (`critical_config_paths` 다음) 및 L56 (`repo_map` 다음)

**추가할 필드:**
```python
# L55 영역에 삽입
mentioned_fnames: list[str]        # algorithm.md §4.3
mentioned_idents: list[str]        # algorithm.md §4.4
chat_file_paths: list[str]         # algorithm.md §4.1 (현재 작업 파일)

# L56 영역에 삽입
definition_ranks: dict             # (file, symbol) → score, algorithm.md §10
symbol_tags: list[dict]            # SymbolTag 목록, algorithm.md §23
repo_map_render: str               # 토큰 예산 맞춘 렌더링 결과, §13
```

- [ ] **Step 2: 테스트 추가**

**파일:** `tests/test_analysis_state.py` (신규)
**assert:** 새 필드가 빈 상태로 접근 가능 (`state.get("mentioned_idents")` → None 또는 [])

- [ ] **Step 3: 검증**

```bash
rtk .venv/bin/pytest tests/test_analysis_state.py -q
```

**Tier:** Flash
**agy:**
```bash
agy -p "src/agenttrace/agents/analysis/state.py의 AnalysisState TypedDict에서 L55 critical_config_paths 다음에 mentioned_fnames: list[str], mentioned_idents: list[str], chat_file_paths: list[str] 필드 3개를 추가하고, L56 repo_map 다음에 definition_ranks: dict, symbol_tags: list[dict], repo_map_render: str 필드 3개를 추가하세요. total=False이므로 모두 optional입니다. 그 다음 tests/test_analysis_state.py를 신규 작성해서 새 필드 6개가 빈 상태로 접근 가능한지(또는 None 반환) 검증하는 테스트를 추가하세요. 검증: rtk .venv/bin/pytest tests/test_analysis_state.py -q" --model "Gemini 3.5 Flash (Low)" --dangerously-skip-permissions
```

---

### Task 1B: 권장 데이터 모델 스키마 추가

- [ ] **Step 1: 스키마 파일 생성**

**파일:** `src/agenttrace/agents/analysis/schemas/repo_map.py` (신규)
**algorithm.md §23 구현:**

```python
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
```

- [ ] **Step 2: 테스트 추가**

**파일:** `tests/test_analysis_schemas_repo_map.py` (신규)
**assert:** 각 모델 인스턴스 생성, 필드 기본값, `model_dump()` 직렬화

- [ ] **Step 3: 검증**

```bash
rtk .venv/bin/pytest tests/test_analysis_schemas_repo_map.py -q
```

**Tier:** Flash

---

### Task 1C: pyproject.toml 의존성 추가

- [ ] **Step 1: 의존성 추가**

**파일:** `pyproject.toml` L11-21 `dependencies` 배열

**추가:**
```toml
"tree-sitter>=0.24.0",
"tree-sitter-python>=0.23.0",
"tree-sitter-javascript>=0.23.0",
"tree-sitter-typescript>=0.23.0",
"tree-sitter-go>=0.23.0",
"tree-sitter-java>=0.23.0",
"tree-sitter-rust>=0.23.0",
"rank-bm25>=0.2.2",
```

- [ ] **Step 2: uv lock 갱신**

```bash
uv lock
```

- [ ] **Step 3: 전체 테스트 호환성 확인**

```bash
rtk .venv/bin/pytest tests/ -q
```

**Tier:** Flash

---

## Phase 2: 파일 수집 전략 변경 (MAX_FILES 제거 + 지연 fetch)

### Task 2A-1: MAX_FILES 제거 및 _filter_blobs로 교체

- [ ] **Step 1: MAX_FILES 제거 및 _select_blobs → _filter_blobs 교체**

**파일:** `src/agenttrace/agents/analysis/github_provider.py`
**위치:** L32 (`MAX_FILES = 300` 제거), L104-117 (`_select_blobs()` 교체)

**교체할 코드 (L104-117):**
```python
def _filter_blobs(blobs: list[dict]) -> list[dict]:
    """전체 파일을 유지하되 critical_config 여부만 태깅한다.

    MAX_FILES 제한 제거 — algorithm.md §22.4.
    내용 fetch는 지연 수행되므로 메타데이터만으로는 비용 미발생.
    """
    for blob in blobs:
        blob["is_critical_config"] = _is_critical_config(blob["path"])
    return blobs
```

**L156 호출부 변경:** `blobs = _select_blobs(all_blobs)` → `blobs = _filter_blobs(all_blobs)`

**Tier:** Flash

---

### Task 2A-2: load()를 load_tree_metadata + fetch_file_contents로 분리

- [ ] **Step 1: load() 메서드 분리**

**파일:** `src/agenttrace/agents/analysis/github_provider.py`
**위치:** L134-182 (`load()` 메서드 교체)

**교체할 코드:**
```python
def load_tree_metadata(
    self, github_url: str, commit_sha: str = "HEAD"
) -> list[dict]:
    """파일 트리 메타데이터만 수집 (내용 fetch 없음)."""
    owner, repo = _parse_owner_repo(github_url)
    tree_url = f"{self.API_BASE}/repos/{owner}/{repo}/git/trees/{commit_sha}?recursive=1"
    resp = self._client.get(tree_url)
    resp.raise_for_status()
    data = resp.json()
    if data.get("truncated"):
        logger.warning("GitHub tree response truncated for %s/%s", owner, repo)
    all_blobs = [
        item for item in data.get("tree", [])
        if item["type"] == "blob"
        and _is_source_file(item["path"], item.get("size", 0))
    ]
    return _filter_blobs(all_blobs)

def fetch_file_contents(
    self, github_url: str, paths: list[str], commit_sha: str = "HEAD"
) -> list[SourceFile]:
    """지정된 경로의 파일 내용만 fetch (지연 로딩)."""
    owner, repo = _parse_owner_repo(github_url)
    source_files: list[SourceFile] = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(self._fetch_file, owner, repo, path, commit_sha): path
            for path in paths
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                sf = future.result()
                if sf:
                    source_files.append(sf)
            except Exception as exc:
                logger.debug("Skip %s: %s", path, exc)
    source_files.sort(key=lambda f: f.path)
    return source_files
```

**Tier:** Standard

---

### Task 2A-3: github_provider 테스트 확장

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_github_provider.py` (기존 확장)
**assert:**
- `load_tree_metadata`가 300개 초과 파일에서도 전체 반환
- `fetch_file_contents`가 지정된 경로만 fetch
- `_filter_blobs`가 `is_critical_config` 태그 추가

- [ ] **Step 2: 검증**

```bash
rtk .venv/bin/pytest tests/test_github_provider.py -q
```

**Tier:** Flash

---

### Task 2B-1: AssembledAnalysisInput 스키마 확장

- [ ] **Step 1: 필드 추가**

**파일:** `src/agenttrace/agents/analysis/schemas/input.py`
**위치:** `AssembledAnalysisInput` 클래스

**추가:** `deferred_file_paths: list[str] = Field(default_factory=list)`

**Tier:** Flash

---

### Task 2B-2: input_providers assemble()에서 지연 fetch 적용

- [ ] **Step 1: assemble() 변경**

**파일:** `src/agenttrace/agents/analysis/input_providers.py`
**위치:** L67-87 (GitHub API 수집 블록)

**변경:** `provider.load()` 호출을 `load_tree_metadata()` + critical_config만 `fetch_file_contents()`로 분리. 나머지는 `deferred_paths`로 전달.

```python
if not source_files and request.repository.github_url:
    from agenttrace.config import get_settings
    from agenttrace.agents.analysis.github_provider import GitHubInputProvider
    settings = get_settings()
    commit_sha = (
        request.snapshot.commit_sha
        if request.snapshot and request.snapshot.commit_sha
        else "HEAD"
    )
    try:
        token = settings.github_token if settings.github_token else None
        provider = GitHubInputProvider(token=token)
        tree_metadata = provider.load_tree_metadata(
            github_url=request.repository.github_url,
            commit_sha=commit_sha,
        )
        critical_paths = [b["path"] for b in tree_metadata if b.get("is_critical_config")]
        source_files = provider.fetch_file_contents(
            github_url=request.repository.github_url,
            paths=critical_paths,
            commit_sha=commit_sha,
        )
        deferred_paths = [b["path"] for b in tree_metadata if not b.get("is_critical_config")]
        input_manifest["source_provider"] = "github_api"
    except Exception as exc:
        missing_inputs.append("github_source_files")
        input_manifest["github_error"] = str(exc)
```

**`AssembledAnalysisInput` 반환 시:** `deferred_file_paths=deferred_paths` 추가

**Tier:** Standard

---

### Task 2B-3: input_providers 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_input_providers.py`
**assert:** `deferred_file_paths`에 critical_config가 포함되지 않음, critical_config 내용이 즉시 fetch됨

**Tier:** Flash

---

### Task 2C: collect_inputs가 deferred_paths 전달

- [ ] **Step 1: return 딕셔너리에 1줄 추가**

**파일:** `src/agenttrace/agents/analysis/nodes/collect_inputs.py`
**위치:** L95-110 return 딕셔너리

**추가:**
```python
"deferred_file_paths": assembled.input_manifest.get("deferred_file_paths", []),
```

**Tier:** Flash

---

### Task 2D: build_file_catalog 대형 트리 테스트

- [ ] **Step 1: 테스트 확장**

**파일:** `tests/test_file_catalog.py`
**assert:** 500개 파일 트리에서 전체 카탈로그 생성, critical_config 분류 정상

**Tier:** Flash

---

## Phase 3: Tree-sitter 심볼 추출 도입 (순차: 3A → 3B → 3C → 3D)

### Task 3A: tags.scm 쿼리 파일 추가

- [ ] **Step 1: 쿼리 파일 4개 생성**

**파일 (신규):**
- `src/agenttrace/agents/analysis/queries/python-tags.scm`
- `src/agenttrace/agents/analysis/queries/typescript-tags.scm`
- `src/agenttrace/agents/analysis/queries/javascript-tags.scm`
- `src/agenttrace/agents/analysis/queries/go-tags.scm`

**내용 (Python 예시, algorithm.md §5.2):**
```scheme
(class_definition
  name: (identifier) @name.definition.class)

(function_definition
  name: (identifier) @name.definition.function)

(call
  function: [
    (identifier) @name.reference.call
    (attribute
      attribute: (identifier) @name.reference.call)
  ])
```

**Tier:** Flash

---

### Task 3B-1: symbol_extractor.py 모듈 骨架

- [ ] **Step 1: 모듈 생성**

**파일:** `src/agenttrace/agents/analysis/symbol_extractor.py` (신규)

**내용:**
```python
from __future__ import annotations
from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
import tree_sitter_javascript as tsjs
import tree_sitter_go as tsgo
from tree_sitter import Language, Parser, Query, QueryCursor

from agenttrace.agents.analysis.schemas.repo_map import SymbolTag

LANGUAGE_MAP = {
    ".py": tspython.language(),
    ".ts": tsts.language_typescript(),
    ".tsx": tsts.language_tsx(),
    ".js": tsjs.language(),
    ".go": tsgo.language(),
}

QUERY_DIR = Path(__file__).parent / "queries"
```

**Tier:** Flash

---

### Task 3B-2: extract_symbols_tree_sitter() 함수 구현

- [ ] **Step 1: 핵심 함수 구현**

**파일:** `src/agenttrace/agents/analysis/symbol_extractor.py`

```python
def extract_symbols_tree_sitter(path: str, content: str) -> list[SymbolTag]:
    """Tree-sitter AST에서 정의/참조 태그 추출."""
    ext = Path(path).suffix
    language = LANGUAGE_MAP.get(ext)
    if not language:
        return _fallback_regex_extract(path, content)

    parser = Parser(language)
    tree = parser.parse(content.encode())
    query_text = (QUERY_DIR / f"{ext[1:]}-tags.scm").read_text()
    query = Query(language, query_text)
    cursor = QueryCursor(query)
    captures = cursor.captures(tree.root_node)

    tags = []
    for node, capture_name in captures:
        name = node.text.decode()
        kind = "definition" if "definition" in capture_name else "reference"
        symbol_kind = capture_name.split(".")[-1]
        tags.append(SymbolTag(
            file_path=path, symbol_name=name,
            symbol_kind=symbol_kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            tag_kind=kind,
        ))
    return tags
```

**Tier:** Standard

---

### Task 3B-3: _fallback_regex_extract() 함수 추가

- [ ] **Step 1: fallback 함수 구현**

**파일:** `src/agenttrace/agents/analysis/symbol_extractor.py`

**내용:** 기존 `repo_map.py`의 `DEF_PATTERNS` regex를 이관하여 Tree-sitter 미지원 언어에서 사용.

**Tier:** Flash

---

### Task 3C-1: repo_map.py가 symbol_extractor 사용하도록 교체

- [ ] **Step 1: extract_symbols() 교체**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L33-43

**교체:**
```python
def extract_symbols(path: str, content: str) -> dict[str, list[str]]:
    tags = extract_symbols_tree_sitter(path, content)
    definitions = sorted({t.symbol_name for t in tags if t.tag_kind == "definition"})
    references = sorted({t.symbol_name for t in tags if t.tag_kind == "reference"})
    return {
        "definitions": definitions,
        "references": references,
        "imports": sorted(_extract_imports(content)),
        "symbol_tags": [t.model_dump() for t in tags],
    }
```

**import 추가:** `from agenttrace.agents.analysis.symbol_extractor import extract_symbols_tree_sitter`

**Tier:** Standard

---

### Task 3C-2: repo_map 테스트 호환성 검증

- [ ] **Step 1: 기존 테스트 호환성 + 신규 assert**

**파일:** `tests/test_analysis_repo_map.py`
**assert:** 기존 테스트 통과 + symbol_tags에 라인 번호 포함

- [ ] **Step 2: 검증**

```bash
rtk .venv/bin/pytest tests/test_analysis_repo_map.py -q
```

**Tier:** Flash

---

### Task 3D: Pygments fallback 참조 추출 추가

- [ ] **Step 1: _pygments_fallback_references() 구현**

**파일:** `src/agenttrace/agents/analysis/symbol_extractor.py`

```python
def _pygments_fallback_references(path: str, content: str) -> list[str]:
    """Tree-sitter 참조 추출이 빈 경우 Pygments Token.Name 보완. §5.4."""
    from pygments import lex
    from pygments.lexers import get_lexer_for_filename
    from pygments.token import Token
    try:
        lexer = get_lexer_for_filename(path)
    except Exception:
        return []
    refs = set()
    for token_type, value in lex(content, lexer):
        if token_type in (Token.Name, Token.Name.Function, Token.Name.Class):
            if len(value) >= 3:
                refs.add(value)
    return sorted(refs)
```

**`extract_symbols_tree_sitter()` 말미:** 참조가 0개일 때 `_pygments_fallback_references()` 호출

**Tier:** Flash

---

## Phase 4: 그래프 및 PageRank 개선 (순차 — 모두 repo_map.py 같은 파일)

> ⚠️ §5-5 파일 비중복: Phase 4의 12개 Task는 모두 `repo_map.py` 수정 → 병렬 불가

### Task 4A-1: 간선 가중치 헬퍼 함수 추가

- [ ] **Step 1: _edge_weight() + _is_named_identifier() 추가**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L83 이전

**추가 (algorithm.md §8):**
```python
def _edge_weight(
    symbol: str,
    reference_count: int,
    *,
    mentioned_idents: set[str],
    chat_file_paths: set[str],
    source_path: str,
    definitions_by_symbol: dict[str, set[str]],
) -> float:
    weight = 1.0
    if symbol.lower() in mentioned_idents:           # §8.1 ×10
        weight *= 10.0
    if len(symbol) >= 8 and _is_named_identifier(symbol):  # §8.2 ×10
        weight *= 10.0
    if symbol.startswith("_"):                       # §8.3 ×0.1
        weight *= 0.1
    if len(definitions_by_symbol.get(symbol.lower(), set())) > 5:  # §8.4 ×0.1
        weight *= 0.1
    if source_path in chat_file_paths:               # §8.5 ×50
        weight *= 50.0
    weight *= math.sqrt(reference_count)             # §8.6
    return weight

def _is_named_identifier(symbol: str) -> bool:
    has_case = any(c.isupper() for c in symbol) and any(c.islower() for c in symbol)
    has_sep = "_" in symbol or "-" in symbol
    return has_case or has_sep
```

**Tier:** Flash

---

### Task 4A-2: _build_edges()에 가중치 적용

- [ ] **Step 1: _build_edges() 교체**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L83-99

**변경:** 간선 추가 시 `+1.0` 대신 `_edge_weight()` 적용. `build_repo_map()` 시그니처에 `mentioned_idents`, `chat_file_paths` 파라미터 추가.

**Tier:** Standard

---

### Task 4A-3: 간선 가중치 테스트

- [ ] **Step 1: 테스트 4개 추가**

**파일:** `tests/test_analysis_repo_map.py`
**assert:**
- mentioned_idents에 있는 심볼 간선이 10배 가중치
- `_` prefix 심볼이 0.1배
- 6개 파일에 정의된 심볼이 0.1배
- sqrt(참조 4회) = ×2 적용

**Tier:** Flash

---

### Task 4B: self-edge 추가 (참조 없는 정의)

- [ ] **Step 1: self-edge 로직 추가**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L92-93 제거 + `_build_edges()` 말미에 추가

**변경:**
- L92-93 `if target_path == source_path: continue` 제거
- `_build_edges()` 말미에 추가:
```python
# §7.4: 참조가 없는 정의에 self-edge (weight=0.1)
for path in files:
    if not edges[path]:
        edges[path][path] = edges[path].get(path, 0.0) + 0.1
```

**Tier:** Flash

---

### Task 4C-1: _rank_definitions() 함수 추가

- [ ] **Step 1: 정의 단위 랭킹 함수 구현**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L173 이후

**추가 (algorithm.md §10):**
```python
def _rank_definitions(
    files: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, float]],
    file_ranks: dict[str, float],
) -> dict[tuple[str, str], float]:
    """파일 PageRank를 정의 단위 점수로 분해. §10."""
    from collections import defaultdict
    definition_scores: dict[tuple[str, str], float] = defaultdict(float)
    for source_path, targets in edges.items():
        total_outgoing = math.fsum(targets.values())
        if total_outgoing <= 0:
            continue
        source_pr = file_ranks.get(source_path, 0.0)
        for target_path, weight in targets.items():
            for symbol in files.get(target_path, {}).get("definitions", []):
                source_refs = {r.lower() for r in files.get(source_path, {}).get("references", [])}
                if symbol.lower() in source_refs:
                    contribution = source_pr * weight / total_outgoing
                    definition_scores[(target_path, symbol)] += contribution
    return dict(definition_scores)
```

**Tier:** Standard

---

### Task 4C-2: build_repo_map() return에 definition_ranks 추가

- [ ] **Step 1: definition_ranks 추가**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L65-72

**추가:**
```python
avg_file_ranks = _average_file_ranks(area_file_ranks)
definition_ranks = _rank_definitions(files, edges, avg_file_ranks)
# return 딕셔너리에 추가:
"definition_ranks": {
    f"{path}::{symbol}": score
    for (path, symbol), score in sorted(definition_ranks.items(), key=lambda x: -x[1])
},
```

**`_average_file_ranks()` 헬퍼도 추가.**

**Tier:** Flash

---

### Task 4C-3: definition_ranks 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_analysis_repo_map.py`
**assert:**
- `definition_ranks`가 `"file::symbol"` 키를 가짐
- 높은 PageRank 파일의 정의가 높은 점수
- 같은 파일 내에서도 심볼별 점수 차이 존재

**Tier:** Flash

---

### Task 4D-1: _rank_files()에 personalization 파라미터 추가

- [ ] **Step 1: _rank_files() 교체**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L146-173

**변경 (algorithm.md §9):** 시그니처에 `personalization: dict[str, float] | None = None` 추가. teleport(0.15)에 personalization vector 사용.

**Tier:** Standard

---

### Task 4D-2: _build_personalization() 헬퍼 추가

- [ ] **Step 1: personalization vector 생성 함수**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`

```python
def _build_personalization(
    files: dict[str, dict[str, Any]],
    mentioned_fnames: list[str],
    mentioned_idents: list[str],
    chat_file_paths: list[str],
) -> dict[str, float]:
    """§9: personalization vector 생성."""
    N = len(files)
    base = 100.0 / N if N else 0.0
    pvec = {path: 0.0 for path in files}
    for path in files:
        if path in chat_file_paths:
            pvec[path] += base
        if path in mentioned_fnames:
            pvec[path] += base
        # 경로 구성요소가 mentioned_idents와 일치
        path_tokens = set(path.lower().replace("/", "_").replace("-", "_").split("_"))
        if path_tokens & {i.lower() for i in mentioned_idents}:
            pvec[path] += base
    return pvec
```

**Tier:** Standard

---

### Task 4D-3: build_repo_map()에서 personalization 전달

- [ ] **Step 1: personalization 생성 후 _rank_files에 전달**

**파일:** `src/agenttrace/agents/analysis/repo_map.py`
**위치:** L65-72

**Tier:** Flash

---

### Task 4D-4: personalization 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_analysis_repo_map.py`
**assert:**
- personalization 지정 파일이 랭킹 상위
- mentioned_idents가 경로에 포함된 파일이 부스트

**Tier:** Flash

---

### Task 4E: build_repo_map 노드가 mentioned_idents/chat_files 전달

- [ ] **Step 1: 노드 함수 파라미터 전달**

**파일:** `src/agenttrace/agents/analysis/nodes/build_repo_map.py`
**위치:** L20-24

**변경:**
```python
repo_map = build_repo_map(
    source_files,
    file_tree=state.get("file_tree", []),
    mentioned_idents=state.get("mentioned_idents", []),
    mentioned_fnames=state.get("mentioned_fnames", []),
    chat_file_paths=state.get("chat_file_paths", []),
)
```

**Tier:** Flash

---

## Phase 5: 영역 매핑 (병렬: 5A 시리즈 || 5B 시리즈 — 서로 다른 파일)

### Task 5A-1: CLAIM_AREA_MAP 및 _infer_area_id 추가

- [ ] **Step 1: 영역 매핑 테이블 + 함수 추가**

**파일:** `src/agenttrace/agents/analysis/nodes/analysis_planner.py`
**위치:** L15 (`REQUIRED_KEYWORDS` 이후)

```python
CLAIM_AREA_MAP: dict[str, str] = {
    "mcp": "agent-and-llm",
    "model context protocol": "agent-and-llm",
    "agent": "agent-and-llm",
    "tool": "tools-and-integrations",
    "prompt": "agent-and-llm",
    "skill": "agent-and-llm",
    "eval": "examples-and-tests",
    "benchmark": "examples-and-tests",
    "docker": "configuration-and-deployment",
    "kubernetes": "configuration-and-deployment",
    "deploy": "configuration-and-deployment",
    "workflow": "configuration-and-deployment",
    "database": "state-and-storage",
    "storage": "state-and-storage",
    "cache": "state-and-storage",
    "memory": "state-and-storage",
    "api": "tools-and-integrations",
    "integration": "tools-and-integrations",
    "service": "architecture-and-modules",
    "module": "architecture-and-modules",
    "entry": "execution-flow",
    "cli": "execution-flow",
    "server": "execution-flow",
    "main": "execution-flow",
}

def _infer_area_id(claim_text: str) -> str:
    lower = claim_text.lower()
    for keyword, area_id in CLAIM_AREA_MAP.items():
        if keyword in lower:
            return area_id
    return "project-purpose"
```

**Tier:** Flash

---

### Task 5A-2: task 생성 시 area_id 주입

- [ ] **Step 1: task 딕셔너리에 area_id 추가**

**파일:** `src/agenttrace/agents/analysis/nodes/analysis_planner.py`
**위치:** L100-118 (required_claims task, optional_claims task 2곳)

**추가:** `"area_id": _infer_area_id(" ".join(c["claim_text"] for c in claim_subset))`

**Tier:** Flash

---

### Task 5A-3: area_id 주입 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_analysis_v2_nodes.py`
**assert:**
- "Provides an MCP server" claim → task에 `"area_id": "agent-and-llm"`
- "Docker deployment" claim → `"configuration-and-deployment"`

**Tier:** Flash

---

### Task 5B-1: extract_mentions 노드 구현

- [ ] **Step 1: 노드 함수 구현**

**파일:** `src/agenttrace/agents/analysis/nodes/extract_mentions.py` (신규)

```python
from __future__ import annotations
import re
import time
from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
PATH_RE = re.compile(r"[\w\-./]+\.\w{1,5}")

def extract_mentions(state: AnalysisState) -> AnalysisState:
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    log = logger.bind(node="extract_mentions", run_id=run_id)
    log.info("시작")

    request = state.get("analysis_request", {}) or {}
    user_message = request.get("user_message", "") or state.get("readme", "")

    mentioned_idents = set(IDENT_RE.findall(user_message))
    mentioned_fnames = set(PATH_RE.findall(user_message))

    tree_paths = {item.get("path", "") for item in state.get("file_tree", [])}
    mentioned_fnames &= tree_paths

    log.info("완료", idents=len(mentioned_idents), fnames=len(mentioned_fnames),
             duration_ms=int((time.perf_counter() - _t) * 1000))
    return {
        "mentioned_idents": sorted(mentioned_idents),
        "mentioned_fnames": sorted(mentioned_fnames),
    }
```

**Tier:** Flash

---

### Task 5B-2: graph.py에 extract_mentions 노드 추가

- [ ] **Step 1: 노드 와이어링**

**파일:** `src/agenttrace/agents/analysis/graph.py`
**위치:** L86-88

**추가:**
```python
builder.add_node("extract_mentions", extract_mentions)
# collect_inputs → extract_mentions → build_file_catalog
builder.add_edge("collect_inputs", "extract_mentions")
builder.add_edge("extract_mentions", "build_file_catalog")
```

**import 추가:** `from agenttrace.agents.analysis.nodes.extract_mentions import extract_mentions`

**Tier:** Flash

---

### Task 5B-3: extract_mentions 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_extract_mentions.py` (신규)
**assert:** 사용자 메시지에서 식별자와 파일 경로 추출, file_tree에 없는 경로는 필터링

**Tier:** Flash

---

## Phase 6: 검색 연동 (BM25 + 임베딩)

### Task 6A-1: BM25 검색 모듈 구현

- [ ] **Step 1: bm25.py 생성**

**파일:** `src/agenttrace/agents/analysis/bm25.py` (신규)

```python
from __future__ import annotations
import re
from rank_bm25 import BM25Okapi

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(text)]

class ChunkBM25Index:
    def __init__(self, chunks: list[dict]):
        self._chunk_ids = [c["chunk_id"] for c in chunks]
        corpus = [
            _tokenize(f"{c.get('file_path', '')} {c.get('content', '')}")
            for c in chunks
        ]
        self._bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(zip(self._chunk_ids, scores), key=lambda x: -x[1])
        return ranked[:top_k]
```

**Tier:** Flash

---

### Task 6A-2: BM25 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_bm25.py` (신규)
**assert:** "agent tool" query가 agent 관련 청크를 상위 반환

**Tier:** Flash

---

### Task 6B-1: 임베딩 유사도 검색 인터페이스 추가

- [ ] **Step 1: search_similar() 추가**

**파일:** `src/agenttrace/services/embeddings.py`
**위치:** L115 이후

**추가:**
```python
class PostgresChunkEmbeddingSql:
    @staticmethod
    def search_similar() -> str:
        return """
            SELECT chunk_id, embedding <=> %(query)s::vector AS distance
            FROM source_chunks
            WHERE snapshot_id = %(snapshot_id)s
            ORDER BY embedding <=> %(query)s::vector
            LIMIT %(top_k)s
        """.strip()

class PostgresChunkEmbeddingStore:
    def search_similar(
        self, query_embedding: list[float], snapshot_id: str, top_k: int = 50
    ) -> list[dict[str, Any]]:
        import json
        return self._connection.execute(
            PostgresChunkEmbeddingSql.search_similar(),
            {"query": json.dumps(query_embedding), "snapshot_id": snapshot_id, "top_k": top_k},
        )
```

**Tier:** Flash

---

### Task 6B-2: 임베딩 검색 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_embeddings.py`
**assert:** `search_similar`이 cosine distance 기반 상위 청크 반환

**Tier:** Flash

---

### Task 6C-1: _hybrid_score() 함수 추가

- [ ] **Step 1: 혼합 스코어링 함수 구현**

**파일:** `src/agenttrace/agents/analysis/nodes/evidence_scout.py`
**위치:** L55 이전

**추가 (algorithm.md §22.3):**
```python
DEFAULT_WEIGHTS = {
    "pagerank": 3.0,
    "bm25": 2.0,
    "embedding": 2.5,
    "path_prior": 1.0,
    "symbol_match": 1.5,
    "artifact_priority": 1.0,
}

def _hybrid_score(
    chunk, *, query_tokens, target_paths, file_ranks, definition_ranks,
    repo_files, bm25_scores, embedding_scores, weights,
) -> float:
    path = chunk.get("file_path", "").lower()
    chunk_id = chunk.get("chunk_id", "")
    score = 0.0
    score += weights["pagerank"] * file_ranks.get(path, 0.0)
    score += weights["bm25"] * bm25_scores.get(chunk_id, 0.0)
    score += weights["embedding"] * embedding_scores.get(chunk_id, 0.0)
    if path in target_paths:
        score += weights["path_prior"]
    repo_file = repo_files.get(path, {})
    symbol_tokens = _tokens(" ".join(repo_file.get("definitions", [])))
    if query_tokens:
        score += weights["symbol_match"] * len(query_tokens & symbol_tokens)
    if repo_file.get("category") == "critical_config":
        score += weights["artifact_priority"]
    return score
```

**Tier:** Standard

---

### Task 6C-2: evidence_scout() 본문에서 혼합 스코어링 적용

- [ ] **Step 1: evidence_scout() 본문 변경**

**파일:** `src/agenttrace/agents/analysis/nodes/evidence_scout.py`
**위치:** L92-167

**변경:**
- `chunk_index`에서 BM25 인덱스 구축
- 임베딩 검색 (embedding_service optional)
- `_chunk_score()` 호출을 `_hybrid_score()`로 교체
- `definition_ranks` 활용

**Tier:** Standard

---

### Task 6C-3: evidence_scout 기존 테스트 rewrite

- [ ] **Step 1: 기존 테스트 조정**

**파일:** `tests/test_analysis_v2_nodes.py`
**변경:** score 구조 변경 반영 (BM25/임베딩 가중치가 0이더라도 기존 assert 통과하도록)

**Tier:** Standard

---

### Task 6C-4: BM25/임베딩 가중치 검증 테스트

- [ ] **Step 1: 신규 테스트 추가**

**파일:** `tests/test_analysis_v2_nodes.py`
**assert:**
- BM25 점수가 높은 청크가 상위 선택
- 임베딩 유사도가 가중치에 반영

**Tier:** Flash

---

## Phase 7: 부가 개선 (병렬: 7A || 7B || 7C — 서로 다른 파일)

### Task 7A-1: mtime 캐시 헬퍼 추가

- [ ] **Step 1: 캐시 함수 추가**

**파일:** `src/agenttrace/agents/analysis/symbol_extractor.py`

```python
import pickle
CACHE_DIR = ".agenttrace.tags.cache"

def _load_cache(path: str, mtime: float) -> list[dict] | None: ...
def _save_cache(path: str, mtime: float, tags: list[dict]) -> None: ...
```

**Tier:** Flash

---

### Task 7A-2: extract_symbols_tree_sitter에 캐시 적용

- [ ] **Step 1: 캐시 적용**

**파일:** `src/agenttrace/agents/analysis/symbol_extractor.py`

**Tier:** Flash

---

### Task 7A-3: mtime 캐시 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_symbol_extractor.py`
**assert:** 같은 mtime은 캐시 hit, mtime 변경 시 재추출

**Tier:** Flash

---

### Task 7B-1: config_parser.py 구현

- [ ] **Step 1: 설정 파일 파서 구현**

**파일:** `src/agenttrace/agents/analysis/config_parser.py` (신규)

**구현 (algorithm.md §22.1):**
- `parse_config_file(path, content) → dict`
- `_parse_package_json()`: dependencies, scripts, entrypoint
- `_parse_pyproject()`: dependencies, build system
- `_parse_dockerfile()`: base_images, commands
- `_parse_github_workflow()`: trigger, steps

**Tier:** Flash

---

### Task 7B-2: build_file_catalog에 config_parser 통합

- [ ] **Step 1: 카탈로그에 설정 파일 구조화 정보 추가**

**파일:** `src/agenttrace/agents/analysis/nodes/build_file_catalog.py`
**위치:** critical_config 분류 시 `parse_config_file()` 호출

**Tier:** Standard

---

### Task 7B-3: config_parser 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_config_parser.py` (신규)
**assert:** package.json dependencies 추출, Dockerfile base image 추출

**Tier:** Flash

---

### Task 7C-1: repo_map_renderer.py 구현

- [ ] **Step 1: 렌더링 모듈 구현**

**파일:** `src/agenttrace/agents/analysis/repo_map_renderer.py` (신규)

**구현 (algorithm.md §13):**
- `render_repo_map(definition_ranks, symbol_tags, max_tokens=1024, special_files=None) → str`
- 이진 탐색으로 토큰 예산 맞춤 (§13.2)
- 15% 허용 오차 (§13.3)
- 각 라인 100자 truncation (§13.6)
- `_count_tokens()` — 긴 경우 샘플링 (§14)

**Tier:** Standard

---

### Task 7C-2: repo_map_renderer 테스트

- [ ] **Step 1: 테스트 추가**

**파일:** `tests/test_repo_map_renderer.py` (신규)
**assert:** 렌더링 결과가 max_tokens 이하, special_files가 맨 앞, 라인이 100자 이하

**Tier:** Flash

---

## Phase 8: 검증 및 통합 (순차)

### Task 8A: 전체 테스트 호환성 검증

- [ ] **Step 1: 전체 테스트 실행**

```bash
rtk .venv/bin/pytest tests/ -q
```

- [ ] **Step 2: 깨지는 테스트 식별 및 수정**

**Tier:** Full

---

### Task 8B: 스펙 동기화 테스트

- [ ] **Step 1: spec sync 확인**

**파일:** `tests/test_spec_sync.py`
**assert:** `AREA_SEEDS` 키가 `COMMON_ANALYSIS_AREAS`와 100% 일치

```bash
rtk .venv/bin/pytest tests/test_spec_sync.py -q
```

**Tier:** Flash

---

### Task 8C: 대형 리포지토리 스모크 테스트

- [ ] **Step 1: Context7 스모크 실행**

```bash
rtk .venv/bin/python -m agenttrace.agents.analysis.cli data/context7_snapshot.json --out out/context7_analysis_v2.json
```

- [ ] **Step 2: 로그 검증**

**검증 항목:**
- `build_repo_map` 로그에 definition_ranks 포함
- `evidence_scout` selected_chunks가 영역별 차별화
- 300개 초과 파일 리포지토리에서 파일 손실 없음
- 최종 status COMPLETED

**Tier:** Standard

---

### Task 8D: 성능 베이스라인 측정

- [ ] **Step 1: 성능 측정**

**측정:**
- `build_repo_map` 노드 duration_ms (Tree-sitter 도입 전후)
- `evidence_scout` 노드 duration_ms (BM25+임베딩 추가 전후)
- 전체 파이프라인 wall time

**기준:** 기존 대비 2배 이내 성능 저하 허용, 정확도 향상이 비용을 상회

**Tier:** Standard

---

## 의존성 그래프

```
Phase 1 (병렬): 1A || 1B || 1C
    ↓
Phase 2 (순차): 2A-1 → 2A-2 → 2A-3 → 2B-1 → 2B-2 → 2B-3 → 2C → 2D
    ↓
Phase 3 (순차): 3A → 3B-1 → 3B-2 → 3B-3 → 3C-1 → 3C-2 → 3D
    ↓
Phase 4 (순차): 4A-1 → 4A-2 → 4A-3 → 4B → 4C-1 → 4C-2 → 4C-3
                → 4D-1 → 4D-2 → 4D-3 → 4D-4 → 4E
    ↓                                        ↓
Phase 5 (병렬): 5A-1 || 5B-1 → 5A-2 || 5B-2 → 5A-3 || 5B-3
    ↓
Phase 6 (병렬+순차): 6A-1 || 6B-1 → 6A-2 || 6B-2 → 6C-1 → 6C-2 → 6C-3 → 6C-4
    ↓
Phase 7 (병렬): 7A-1 || 7B-1 || 7C-1 → 7A-2 || 7B-2 || 7C-2 → 7A-3 || 7B-3
    ↓
Phase 8 (순차): 8A → 8B → 8C → 8D
```

---

## 리스크 및 완화

| 리스크 | 완화 |
|---|---|
| Tree-sitter 의존성 추가로 uv.lock 갱신 필요 | Task 1C에서 `uv lock` 검증 |
| github_provider 변경이 기존 테스트 호환성 깨기 | Task 2A-3에서 기존 assert 유지 |
| BM25/임베딩이 evidence_scout 성능 저하 | DEFAULT_WEIGHTS로 점진적 도입, 임베딩은 optional |
| Tree-sitter 언어 바인딩 버전 호환성 | Task 1C에서 설치 후 import 테스트 |
| Phase 4 순차 실행 12 Task로 wall time 길어짐 | 각 Task를 최소 단위로 유지, Flash tier 활용 |
| 정의 단위 랭킹 계산 복잡도 | _rank_definitions는 파일 수 × 심볼 수, 실측 후 최적화 |

---

## Self-Review

- **Spec coverage:** algorithm.md §5-22의 16개 항목 전부 커버
  - §5.2 Tree-sitter: Task 3A-3D
  - §7.4 self-edge: Task 4B
  - §8 가중치 6종: Task 4A-1~4A-3
  - §9 Personalized PageRank: Task 4D-1~4D-4
  - §10 정의 단위 랭킹: Task 4C-1~4C-3
  - §22.1 설정 파일 구조화: Task 7B-1~7B-3
  - §22.3 BM25+임베딩: Task 6A-6C
  - §22.4 파일 영구 제거 금지: Task 2A-1~2A-2
  - §13 토큰 예산 렌더링: Task 7C-1~7C-2
- **Placeholder scan:** TBD/TODO 없음
- **Type consistency:** repo_map 필드명 (`definition_ranks`, `symbol_tags`)이 state.py, schemas, evidence_scout에서 일관됨
- **Task 세분화:** 각 Task는 단일 함수 추가·교체 수준 (§5-1)
- **병렬 안전성:** 같은 파일 수정 Task는 병렬 배치하지 않음 (§5-5)
