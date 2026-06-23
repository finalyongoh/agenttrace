from uuid import uuid4

from agenttrace.agents.analysis.graph import build_graph


class RecordingContentIndexStore:
    def __init__(self):
        self.requests = []

    def request_index(self, **kwargs):
        self.requests.append(kwargs)
        return {"index_id": "idx-1", "status": "COMPLETED"}


class RecordingEmbeddingService:
    def __init__(self):
        self.texts = []

    def embed_texts(self, texts):
        self.texts.extend(texts)
        return [[0.1] * 1536 for _ in texts]


class RecordingEmbeddingStore:
    def __init__(self):
        self.rows = []

    def update_embeddings(self, rows):
        self.rows.extend(rows)
        return [{"chunk_id": row["chunk_id"]} for row in rows]


def test_analysis_v2_graph_limited_path_completes_with_insufficient_evidence():
    graph = build_graph()
    result = graph.invoke(
        {
            "analysis_request": {
                "analysis_id": str(uuid4()),
                "repository": {"full_name": "owner/repo", "github_url": "https://github.com/owner/repo"},
                "snapshot": {"snapshot_id": "snap-1"},
                "readme_text": "# Repo\nProvides an MCP server.",
                "file_tree": ["README.md", "src/server.py"],
                "external_ingest": {"enabled": False, "provider": "gitingest"},
            },
            "claims": [],
            "evidence_signals": [],
            "risk_signals": [],
            "quality_warnings": [],
            "quality_errors": [],
            "task_results": [],
            "task_traces": [],
        }
    )

    assert result["final_result"]["analysis_status"] in {"insufficient_evidence", "completed_with_limitations"}
    assert result["callback_payload"]["analysis_result"]["analysis_limitations"]["missing_inputs"]


def test_analysis_v2_graph_accepts_content_index_and_embedding_dependencies():
    content_store = RecordingContentIndexStore()
    embedding_service = RecordingEmbeddingService()
    embedding_store = RecordingEmbeddingStore()
    graph = build_graph(
        content_index_store=content_store,
        embedding_service=embedding_service,
        embedding_store=embedding_store,
    )

    result = graph.invoke(
        {
            "analysis_request": {
                "analysis_id": str(uuid4()),
                "repository": {"full_name": "owner/repo", "github_url": "https://github.com/owner/repo"},
                "snapshot": {"snapshot_id": "snap-1"},
                "readme_text": "# Repo\nProvides an MCP server.",
                "file_tree": ["README.md", "src/server.py"],
                "source_files": [{"path": "src/server.py", "content": "def register_tool(): pass"}],
                "external_ingest": {"enabled": False, "provider": "gitingest"},
            },
            "claims": [],
            "evidence_signals": [],
            "risk_signals": [],
            "quality_warnings": [],
            "quality_errors": [],
            "task_results": [],
            "task_traces": [],
        }
    )

    assert content_store.requests[0]["snapshot_id"] == "snap-1"
    assert embedding_service.texts == ["def register_tool(): pass"]
    assert embedding_store.rows[0]["chunk_id"] == result["content_chunks"][0]["chunk_id"]
