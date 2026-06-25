from agenttrace.agents.analysis.bm25 import ChunkBM25Index


def test_bm25_returns_relevant_chunks_first():
    chunks = [
        {"chunk_id": "c1", "file_path": "src/agent.py", "content": "class Agent:\n    def run(self):\n        tool.call()"},
        {"chunk_id": "c2", "file_path": "src/utils.py", "content": "def helper():\n    return 42"},
        {"chunk_id": "c3", "file_path": "src/tool.py", "content": "class Tool:\n    def call(self):\n        pass"},
    ]
    index = ChunkBM25Index(chunks)
    results = index.search("agent tool", top_k=3)

    assert len(results) > 0
    top_chunk_id = results[0][0]
    # agent 또는 tool 관련 청크가 상위에 와야 함
    assert top_chunk_id in {"c1", "c3"}


def test_bm25_empty_chunks_returns_empty():
    index = ChunkBM25Index([])
    assert index.search("test") == []


def test_bm25_empty_query_returns_empty():
    chunks = [{"chunk_id": "c1", "file_path": "src/a.py", "content": "def foo(): pass"}]
    index = ChunkBM25Index(chunks)
    assert index.search("") == []


def test_bm25_get_scores_dict():
    chunks = [
        {"chunk_id": "c1", "file_path": "src/agent.py", "content": "agent tool prompt model context"},
        {"chunk_id": "c2", "file_path": "src/utils.py", "content": "helper function for formatting"},
        {"chunk_id": "c3", "file_path": "src/config.py", "content": "configuration settings loader"},
        {"chunk_id": "c4", "file_path": "src/test.py", "content": "test fixture for agent"},
    ]
    index = ChunkBM25Index(chunks)
    scores = index.get_scores_dict("agent tool")

    assert scores["c1"] > scores.get("c2", 0.0)
