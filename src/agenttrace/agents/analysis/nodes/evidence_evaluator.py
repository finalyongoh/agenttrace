from __future__ import annotations

import re
import json
import logging
from typing import Literal

from pydantic import BaseModel, Field
from agenttrace.agents.analysis.schemas.result import ClaimVerdict, EvidenceSignal
from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.models import build_openai_summary_model
from agenttrace.config import get_settings
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


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


def _fallback_evaluate(claims: list[dict], chunks: list[dict], evidence_signals: list[dict], verdicts: list[dict], start_idx: int = 1) -> None:
    for claim in claims:
        claim_tokens = _tokens(claim.get("claim_text", ""))
        
        # Find the chunk with the most keyword overlap for this specific claim
        best_chunk = None
        best_overlap_len = 0
        best_overlap = set()
        
        for chunk in chunks:
            chunk_content = f"{chunk.get('file_path', '')}\n{chunk.get('content', '')}"
            chunk_tokens = _tokens(chunk_content)
            overlap = claim_tokens & chunk_tokens
            if len(overlap) > best_overlap_len:
                best_overlap_len = len(overlap)
                best_chunk = chunk
                best_overlap = overlap

        signal_ids: list[str] = []
        if best_chunk and best_overlap_len > 0:
            chunk = best_chunk
            overlap = best_overlap
            signal = EvidenceSignal(
                signal_id=f"signal-{start_idx + len(evidence_signals):04d}",
                signal_type="SOURCE_CHUNK",
                path=chunk["file_path"],
                chunk_id=chunk["chunk_id"],
                line_start=chunk["line_start"],
                line_end=chunk["line_end"],
                content_excerpt=chunk.get("content", "")[:500],
                content_hash=chunk["content_hash"],
                summary="Source chunk overlaps README claim keywords.",
                confidence=min(0.55 + (0.05 * len(overlap)), 0.9),
            )
            evidence_signals.append(signal.model_dump())
            signal_ids.append(signal.signal_id)
            verdict = "SUPPORTED" if len(overlap) >= 2 else "PARTIALLY_SUPPORTED"
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
    task = _current_task(state)
    if not task:
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

    for part in task_parts:
        part_chunk_ids = part.get("chunks", [])
        chunks = [chunks_by_id[cid] for cid in part_chunk_ids if cid in chunks_by_id]
        
        evidence_signals: list[dict] = []
        verdicts: list[dict] = []
        llm_success = False
        
        if settings.openai_api_key and chunks and claims:
            try:
                model = build_openai_summary_model()
                structured_model = model.with_structured_output(BatchVerificationResult)
                
                # Format chunks and claims for the prompt
                claims_formatted = json.dumps([
                    {"claim_id": c["claim_id"], "claim_text": c["claim_text"]}
                    for c in claims
                ], ensure_ascii=False, indent=2)
                
                chunks_formatted = ""
                for idx, chunk in enumerate(chunks):
                    chunks_formatted += f"--- Chunk {idx + 1} (File: {chunk['file_path']}) ---\n"
                    chunks_formatted += f"{chunk.get('content', '')}\n---\n\n"
                    
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are an expert AI software analyst. Your task is to verify technical claims made in a project's README against the provided source code chunks.\nFor each claim, analyze if the code chunks support, partially support, contradict, or do not contain information about the claim.\nReturn a structured verdict for each claim. Specify the correct file_path, line_start, line_end, and a short content_excerpt if supported or partially supported."),
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
                            signal = EvidenceSignal(
                                signal_id=f"signal-{start_idx + len(evidence_signals):04d}",
                                signal_type="SOURCE_CHUNK",
                                path=v.file_path,
                                chunk_id=matching_chunk["chunk_id"],
                                line_start=v.line_start or matching_chunk["line_start"],
                                line_end=v.line_end or matching_chunk["line_end"],
                                content_excerpt=v.content_excerpt or matching_chunk.get("content", "")[:500],
                                content_hash=matching_chunk["content_hash"],
                                summary="Source code verified by LLM semantic analysis.",
                                confidence=0.85 if verdict_status == "SUPPORTED" else 0.70,
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
                logger.warning(f"LLM claims evaluation failed for part {part['part_id']}, falling back to keyword logic: {exc}")
                evidence_signals = []
                verdicts = []
                
        if not llm_success:
            _fallback_evaluate(claims, chunks, evidence_signals, verdicts, start_idx=start_idx)

        start_idx += len(evidence_signals)

        task_part_results.append({
            "part_id": part["part_id"],
            "task_id": task["task_id"],
            "evidence_signals": evidence_signals,
            "claim_verdicts": verdicts,
        })

    return {
        "task_part_results": task_part_results
    }
