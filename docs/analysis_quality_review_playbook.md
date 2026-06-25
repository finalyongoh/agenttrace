# Analysis Quality Review Playbook

This playbook defines the local review workflow for AgentTrace Analysis output. Use it with `docs/analysis_evidence_policy.md` and `docs/analysis_run_artifact_contract.md`.

## Review Workflow

1. Sync `docs/reference` with `rtk git -C docs/reference pull`.
2. Identify the target repository, repository owner/name, and exact commit SHA. Do not review against the current default branch unless the run artifact explicitly targets that commit.
3. Collect the run bundle: structured result JSON, final markdown report, trace, source snapshot manifest, evidence refs, evidence signals, model or prompt versions, and the analysis version.
4. Separate four inputs before judging quality: target spec, current implementation, actual run artifact, and reviewer judgment.
5. Independently inspect source excerpts for any `confirmed` or code-specific claim. Repo maps, file trees, README files, and summary text are discovery aids, not sufficient evidence for `confirmed`.
6. Audit each area finding, report section, Mermaid diagram, limitation, and follow-up recommendation against the evidence policy.
7. Record critical errors with file paths, line ranges, mismatched excerpts, and the affected finding or report section.

## Evidence Rules

Apply `docs/analysis_evidence_policy.md` exactly. A `confirmed` finding requires direct source evidence when source content exists. Static analysis must not present runtime behavior, security posture, production reliability, or performance as certain without measured runtime evidence.

## Review Output Format

Use this structure for reviewer notes:

- `run_identity`: target repo, commit SHA, analysis version, model or prompt version.
- `artifact_completeness`: present and missing files from the run contract.
- `critical_errors`: invented files/functions, excerpt mismatch, line mismatch, source-less code claims, tests mistaken as implementation, or static certainty errors.
- `finding_audit`: per finding status of `confirmed`, `partially_confirmed`, `unconfirmed`, or `not_applicable`.
- `limitations`: missing source content, deferred paths, unavailable trace, or other constraints.
- `verdict`: pass, pass with limitations, or fail.

## Review Boundaries

The reviewer judges the actual run artifact, not what the implementation might have produced under different inputs. If source content is missing, mark that limitation explicitly and downgrade unsupported code claims instead of filling gaps from assumptions.
