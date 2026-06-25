# Analysis Run Artifact Contract

This contract defines the minimum artifacts needed to evaluate one AgentTrace Analysis run.

## Run Artifact Contract

An evaluation bundle must identify the exact target and contain enough structured evidence for independent review. Missing source content is a first-class limitation, not a normal completed state.

## Minimum Run Bundle

Each reviewable run should include:

- Target repository URL or full name.
- Target commit SHA.
- Source snapshot manifest with source file count, missing inputs, provider name, and deferred paths.
- Structured result JSON.
- Final markdown report.
- Evidence refs and evidence signals.
- Tool-call trace, or an explicit note that tool-call trace is unavailable.
- Model version, prompt version, and analysis version.
- Precheck result, quality gate result, and analysis limitations.

## Missing Source Content

When source content is missing, truncated, deferred, or unavailable, the run must expose that state in `input_manifest`, `precheck_result`, `analysis_limitations`, or the trace. Reviewers must downgrade unsupported implementation claims and record the missing input as a limitation.

## Trace Fields

`persist_analysis` should preserve these trace fields in the callback payload:

- `input_manifest`
- `precheck_result`
- `evidence_refs`
- `evidence_signals`
- `analysis_limitations`
- `quality_gate_result`
- `final_result`
- `analysis_version`

Adding fields is backward-compatible. Removing or renaming the callback envelope is not part of this contract.
