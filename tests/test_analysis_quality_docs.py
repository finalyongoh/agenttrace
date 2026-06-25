from pathlib import Path


REQUIRED_DOC_SECTIONS = {
    "docs/analysis_quality_review_playbook.md": [
        "Review Workflow",
        "Evidence Rules",
        "Review Output Format",
    ],
    "docs/analysis_evidence_policy.md": [
        "Evidence Status Policy",
        "Critical Error Checklist",
        "Source Hierarchy",
    ],
    "docs/analysis_run_artifact_contract.md": [
        "Run Artifact Contract",
        "Minimum Run Bundle",
        "Missing Source Content",
    ],
}


def test_analysis_quality_docs_exist_with_required_sections():
    for doc_path, sections in REQUIRED_DOC_SECTIONS.items():
        content = Path(doc_path).read_text(encoding="utf-8")

        for section in sections:
            assert f"## {section}" in content, f"{doc_path} is missing section: {section}"


def test_quality_playbook_links_policy_and_run_contract():
    content = Path("docs/analysis_quality_review_playbook.md").read_text(encoding="utf-8")

    assert "docs/analysis_evidence_policy.md" in content
    assert "docs/analysis_run_artifact_contract.md" in content
    assert "target spec" in content
    assert "current implementation" in content
    assert "actual run artifact" in content
    assert "reviewer judgment" in content
