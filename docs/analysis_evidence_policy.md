# Analysis Evidence Policy

This policy defines evidence status and critical errors for AgentTrace Analysis reviews.

## Evidence Status Policy

Use these statuses consistently:

- `confirmed`: at least one valid code, config, or documentation evidence ref supports the claim. When source content exists, the evidence ref must include a real path, `line_start`, `line_end`, `content_excerpt`, and `content_hash`.
- `partially_confirmed`: evidence supports the direction of the claim, but direct implementation proof is missing, the proof is only docs/config, or the excerpt is too indirect for full confirmation.
- `unconfirmed`: no direct evidence supports the claim, the referenced source is unavailable, or the artifact only provides repo map/file tree/README discovery data.
- `not_applicable`: the area is genuinely outside the target repository scope or technology stack.

## Critical Error Checklist

Treat any of these as critical:

- Invented file path, function, class, endpoint, configuration key, or package.
- Evidence excerpt does not match the referenced source content.
- Line range does not contain the cited claim or excerpt.
- Code-specific claim has no source excerpt when source content was available.
- Test, fixture, example, or documentation is mistaken for production implementation.
- Runtime behavior, security posture, performance, production reliability, or deployment success is stated with static certainty.
- Repo map, file tree, README, or package metadata is used as the only proof for a `confirmed` implementation claim.

## Source Hierarchy

Prefer evidence in this order:

1. Source excerpt from implementation code.
2. Configuration, dependency, schema, migration, or build file.
3. Project docs, README, examples, or tests, with status downgraded when they do not prove implementation.
4. Repo map, symbol map, file tree, or generated summary as discovery only.

## Evidence Ref Shape

For source-backed evidence, reviewers should expect:

```json
{
  "path": "src/example.py",
  "line_start": 10,
  "line_end": 16,
  "content_excerpt": "def run():",
  "content_hash": "sha256:..."
}
```

If source content is unavailable, the run must say so through limitations and should not mark code-specific claims as `confirmed`.
