from pathlib import Path
import re
import json
import time
from typing import Literal

from pydantic import BaseModel, Field
from agenttrace.agents.analysis.schemas.result import ClaimVerdict, EvidenceSignal
from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.models import build_openai_analysis_model
from agenttrace.config import get_settings
from langchain_core.prompts import ChatPromptTemplate
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)


def _get_chunk_content(chunk: dict, local_repo_dir: Path | None, file_bytes_cache: dict[Path, bytes] | None = None) -> str:
    if chunk.get("content"):
        return chunk["content"]
    if not local_repo_dir:
        return ""
    file_path_str = chunk.get("file_path")
    if not file_path_str:
        return ""
    try:
        resolved_base = local_repo_dir.resolve()
        resolved_target = (local_repo_dir / file_path_str).resolve()
        if not resolved_target.is_relative_to(resolved_base):
            raise ValueError(f"Path traversal detected: {file_path_str}")

        file_path = local_repo_dir / file_path_str
        if file_path.exists():
            if file_bytes_cache is not None and file_path in file_bytes_cache:
                content_bytes = file_bytes_cache[file_path]
            else:
                content_bytes = file_path.read_bytes()
                if file_bytes_cache is not None:
                    file_bytes_cache[file_path] = content_bytes
            start_byte = chunk.get("start_byte", 0)
            end_byte = chunk.get("end_byte", 0)
            return content_bytes[start_byte:end_byte].decode("utf-8", errors="ignore")
    except Exception as exc:
        if "Path traversal detected" in str(exc):
            raise
        pass
    return ""


class ClaimVerification(BaseModel):
    claim_id: str
    verdict: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "NOT_FOUND"] = Field(
        description="Whether the claim is fully supported, partially supported, contradicted, or not found in the code chunks."
    )
    reason: str = Field(description="Detailed explanation of why this verdict was chosen based on the code.")
    file_path: str | None = Field(default=None, description="The path of the file containing the code evidence, or null.")
    line_start: int | None = Field(default=None, description="1-based starting line number of the code evidence, or null.")
    line_end: int | None = Field(default=None, description="1-based ending line number of the code evidence, or null.")
    content_excerpt: str | None = Field(default=None, description="A 2-3 line code snippet showing the evidence, or null.")


class BatchVerificationResult(BaseModel):
    verdicts: list[ClaimVerification] = Field(description="List of verification verdicts for each claim.")


def _current_task(state: AnalysisState) -> dict | None:
    task_id = state.get("current_task_id")
    for task in state.get("analysis_plan", {}).get("tasks", []):
        if task.get("task_id") == task_id:
            return task
    return None


def _tokens(text: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"[_\W]+", " ", spaced)
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]{2,}", spaced)}


def _format_chunk_with_line_numbers(chunk_text: str, start_line: int) -> str:
    lines = chunk_text.splitlines()
    formatted_lines = []
    for i, line in enumerate(lines):
        formatted_lines.append(f"{start_line + i}: {line}")
    return "\n".join(formatted_lines)


def _infer_signal_type(file_path: str) -> str:
    lower_path = file_path.lower()
    if lower_path.endswith((".md", ".mdx", ".txt")):
        return "DOCUMENTATION_CORROBORATION"
    elif lower_path.endswith((".yml", ".yaml", ".json", ".toml", "dockerfile")) or "docker-compose" in lower_path:
        return "CONFIGURATION_EVIDENCE"
    elif lower_path.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".sh", ".rs", ".java", ".c", ".cpp", ".h")):
        return "IMPLEMENTATION_EVIDENCE"
    else:
        return "METADATA_SIGNAL"


def _fallback_evaluate(
    claims: list[dict],
    chunks: list[dict],
    evidence_signals: list[dict],
    verdicts: list[dict],
    start_idx: int = 1,
    local_repo_dir: Path | None = None,
    file_bytes_cache: dict[Path, bytes] | None = None,
) -> None:
    for claim in claims:
        claim_tokens = _tokens(claim.get("claim_text", ""))
        
        # Find the chunk with the most keyword overlap for this specific claim
        best_chunk = None
        best_overlap_len = 0
        best_overlap = set()
        best_chunk_content = ""
        
        for chunk in chunks:
            chunk_text = _get_chunk_content(chunk, local_repo_dir, file_bytes_cache)
            chunk_content = f"{chunk.get('file_path', '')}\n{chunk_text}"
            chunk_tokens = _tokens(chunk_content)
            overlap = claim_tokens & chunk_tokens
            if len(overlap) > best_overlap_len:
                best_overlap_len = len(overlap)
                best_chunk = chunk
                best_overlap = overlap
                best_chunk_content = chunk_text

        signal_ids: list[str] = []
        if best_chunk and best_overlap_len > 0:
            chunk = best_chunk
            overlap = best_overlap
            
            sig_type = _infer_signal_type(chunk["file_path"])
            verdict = "SUPPORTED" if len(overlap) >= 2 else "PARTIALLY_SUPPORTED"
            
            if sig_type == "DOCUMENTATION_CORROBORATION" and verdict == "SUPPORTED":
                verdict = "DOCUMENTED"
                
            signal = EvidenceSignal(
                signal_id=f"signal-{start_idx + len(evidence_signals):04d}",
                signal_type=sig_type,
                path=chunk["file_path"],
                chunk_id=chunk["chunk_id"],
                line_start=chunk["line_start"],
                line_end=chunk["line_end"],
                content_excerpt=best_chunk_content[:500],
                content_hash=chunk["content_hash"],
                summary="Source chunk overlaps README claim keywords.",
                confidence=min(0.55 + (0.05 * len(overlap)), 0.9),
            )
            evidence_signals.append(signal.model_dump())
            signal_ids.append(signal.signal_id)
            reason = "Selected source chunk contains terms related to the claim."
            limitations: list[str] = []
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            reason = "No source chunk was available for this claim."
            limitations = ["source content unavailable or no relevant chunk selected"]

        verdicts.append(ClaimVerdict(
            claim_id=claim["claim_id"],
            verdict=verdict,
            reason=reason,
            evidence_signal_ids=signal_ids,
            limitations=limitations,
        ).model_dump())


def evidence_evaluator(state: AnalysisState) -> AnalysisState:
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    task_id = state.get("current_task_id", "-")
    log = logger.bind(node="evidence_evaluator", run_id=run_id, task_id=task_id)
    log.info("시작")
    task = _current_task(state)
    if not task:
        log.info("완료", results=0, duration_ms=int((time.perf_counter() - _t) * 1000))
        return {"task_part_results": []}

    all_chunks = state.get("selected_chunks", [])
    chunks_by_id = {c["chunk_id"]: c for c in all_chunks}
    
    claims = [
        claim for claim in state.get("claims", [])
        if claim.get("claim_id") in set(task.get("claims", []))
    ]

    settings = get_settings()
    task_part_results = []
    
    start_idx = len(state.get("evidence_signals", [])) + 1
    
    task_parts = state.get("task_parts", [])
    if not task_parts:
        task_parts = [{
            "part_id": f"{task['task_id']}-part-001",
            "task_id": task["task_id"],
            "chunks": [c["chunk_id"] for c in all_chunks]
        }]

    local_repo_dir_str = state.get("local_repo_dir")
    local_repo_dir = Path(local_repo_dir_str) if local_repo_dir_str else None
    file_bytes_cache: dict[Path, bytes] = {}

    for part in task_parts:
        part_chunk_ids = part.get("chunks", [])
        chunks = [chunks_by_id[cid] for cid in part_chunk_ids if cid in chunks_by_id]
        
        evidence_signals: list[dict] = []
        verdicts: list[dict] = []
        llm_success = False
        
        if settings.openai_api_key and chunks and claims:
            try:
                model = build_openai_analysis_model()
                structured_model = model.with_structured_output(BatchVerificationResult)
                
                # Format chunks and claims for the prompt
                claims_formatted = json.dumps([
                    {"claim_id": c["claim_id"], "claim_text": c["claim_text"]}
                    for c in claims
                ], ensure_ascii=False, indent=2)
                
                chunks_formatted = ""
                for idx, chunk in enumerate(chunks):
                    chunk_text = _get_chunk_content(chunk, local_repo_dir, file_bytes_cache)
                    start_line = chunk.get("line_start", 1)
                    formatted_chunk_text = _format_chunk_with_line_numbers(chunk_text, start_line)
                    chunks_formatted += f"--- Chunk {idx + 1} (File: {chunk['file_path']}) ---\n"
                    chunks_formatted += f"{formatted_chunk_text}\n---\n\n"
                    
                prompt = ChatPromptTemplate.from_messages([
                    ("system", (
                        "You are an expert AI software analyst. Your task is to verify technical claims made in a project's README against the provided source code chunks.\n"
                        "Each line of a source code chunk is prefixed with its absolute line number in the file (e.g. '123: class MyClass:'). "
                        "When returning the verification result, you MUST extract and return the correct absolute line_start and line_end values matching the code evidence.\n"
                        "For each claim, analyze if the chunks support, partially support, contradict, or do not contain information about the claim.\n"
                        "CRITICAL VERDICT RULES:\n"
                        "1. Do NOT mark a claim as fully `SUPPORTED` if the only evidence is a deployment/workflow file (like a GitHub workflow, CI/CD configuration, or Docker Compose), or a metadata setup. Such setup files only prove configuration, not actual logic implementation. Mark them as `PARTIALLY_SUPPORTED` at best.\n"
                        "2. Do NOT mark a claim as fully `SUPPORTED` if the evidence only shows basic variables or environment settings (like checking for an API key environment variable, but not implementing the actual OAuth flow). Mark as `PARTIALLY_SUPPORTED` or `INSUFFICIENT_EVIDENCE`.\n"
                        "3. Purely descriptive text inside documentation (like Markdown, MDX, or text files) should be evaluated, but avoid marking them as fully `SUPPORTED` if they only claim the feature exists without showing source code logic."
                    )),
                    ("human", "Claims to Verify:\n{claims_formatted}\n\nSource Code Chunks:\n{chunks_formatted}")
                ])
                
                prompt_value = prompt.invoke({
                    "claims_formatted": claims_formatted,
                    "chunks_formatted": chunks_formatted
                })
                
                result = structured_model.invoke(prompt_value)
                
                for v in result.verdicts:
                    signal_ids = []
                    verdict_status = v.verdict
                    limitations = []
                    
                    if verdict_status in ["SUPPORTED", "PARTIALLY_SUPPORTED"] and v.file_path:
                        matching_chunk = next(
                            (c for c in chunks if c["file_path"].lower() == v.file_path.lower()),
                            chunks[0] if chunks else None
                        )
                        
                        if matching_chunk:
                            sig_type = _infer_signal_type(v.file_path)
                            
                            # Downgrade verdict to DOCUMENTED if it was SUPPORTED and the only evidence is documentation
                            if sig_type == "DOCUMENTATION_CORROBORATION" and verdict_status == "SUPPORTED":
                                verdict_status = "DOCUMENTED"
                            
                            chunk_line_start = matching_chunk.get("line_start", 1)
                            chunk_line_end = matching_chunk.get("line_end", 1)
                            
                            line_start = v.line_start
                            line_end = v.line_end
                            
                            # Clamp line numbers if they fall outside the boundaries
                            if not line_start or line_start < chunk_line_start or line_start > chunk_line_end:
                                line_start = chunk_line_start
                            if not line_end or line_end < line_start or line_end > chunk_line_end:
                                line_end = chunk_line_end

                            signal = EvidenceSignal(
                                signal_id=f"signal-{start_idx + len(evidence_signals):04d}",
                                signal_type=sig_type,
                                path=v.file_path,
                                chunk_id=matching_chunk["chunk_id"],
                                line_start=line_start,
                                line_end=line_end,
                                content_excerpt=v.content_excerpt or _get_chunk_content(matching_chunk, local_repo_dir, file_bytes_cache)[:500],
                                content_hash=matching_chunk["content_hash"],
                                summary="Source code verified by LLM semantic analysis.",
                                confidence=0.85 if verdict_status in ["SUPPORTED", "DOCUMENTED"] else 0.70,
                            )
                            evidence_signals.append(signal.model_dump())
                            signal_ids.append(signal.signal_id)
                    else:
                        verdict_status = "INSUFFICIENT_EVIDENCE"
                        limitations = ["LLM semantic analysis could not verify this claim from the code chunks"]
                    
                    verdicts.append(ClaimVerdict(
                        claim_id=v.claim_id,
                        verdict=verdict_status,
                        reason=v.reason,
                        evidence_signal_ids=signal_ids,
                        limitations=limitations,
                    ).model_dump())
                    
                llm_success = True
            except Exception as exc:
                log.warning("LLM 검증 실패 (fallback)", part_id=part['part_id'], error=str(exc))
                evidence_signals = []
                verdicts = []
                
        if not llm_success:
            _fallback_evaluate(
                claims,
                chunks,
                evidence_signals,
                verdicts,
                start_idx=start_idx,
                local_repo_dir=local_repo_dir,
                file_bytes_cache=file_bytes_cache,
            )

        start_idx += len(evidence_signals)

        task_part_results.append({
            "part_id": part["part_id"],
            "task_id": task["task_id"],
            "evidence_signals": evidence_signals,
            "claim_verdicts": verdicts,
        })

    total_signals = sum(len(r.get("evidence_signals", [])) for r in task_part_results)
    total_verdicts = sum(len(r.get("claim_verdicts", [])) for r in task_part_results)
    log.info("완료", task_parts=len(task_parts), signals=total_signals, verdicts=total_verdicts, duration_ms=int((time.perf_counter() - _t) * 1000))
    return {
        "task_part_results": task_part_results
    }
