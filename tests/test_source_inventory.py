from pathlib import Path

from agenttrace.agents.analysis.source_inventory import SourceInventory


def test_source_inventory_builds_hash_and_line_excerpt_from_source_files():
    inventory = SourceInventory.from_source_files(
        [
            {
                "path": "src/app.py",
                "content": "def one():\n    return 1\n\ndef two():\n    return 2\n",
            }
        ]
    )

    ref = inventory.build_evidence_ref(
        ref_id="ref-1",
        path="src/app.py",
        line_start=1,
        line_end=2,
        source_type="code",
        description="one function",
    )

    assert ref["content_excerpt"] == "def one():\n    return 1"
    assert ref["content_hash"].startswith("sha256:")
    assert ref["line_start"] == 1
    assert ref["line_end"] == 2


def test_source_inventory_validates_evidence_ref_against_real_content():
    inventory = SourceInventory.from_source_files(
        [{"path": "src/app.py", "content": "alpha\nbeta\ngamma\n"}]
    )
    ref = inventory.build_evidence_ref(
        ref_id="ref-1",
        path="src/app.py",
        line_start=2,
        line_end=2,
        source_type="code",
        description="beta line",
    )

    assert inventory.validate_evidence_ref(ref) == []

    ref["content_excerpt"] = "not beta"
    assert "excerpt mismatch" in inventory.validate_evidence_ref(ref)[0]


def test_source_inventory_can_load_from_directory(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.ts").write_text("export const tool = true;\n", encoding="utf-8")

    inventory = SourceInventory.from_directory(tmp_path, ["src/agent.ts"])

    assert inventory.records["src/agent.ts"].content == "export const tool = true;\n"
    assert inventory.records["src/agent.ts"].content_hash.startswith("sha256:")
