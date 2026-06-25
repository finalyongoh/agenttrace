from agenttrace.agents.analysis.symbol_extractor import extract_symbols_tree_sitter


def test_python_class_and_function_definitions():
    code = "class Agent:\n    def run(self):\n        pass\n\ndef create_agent():\n    pass\n"
    tags = extract_symbols_tree_sitter("src/agent.py", code)

    defs = {t.symbol_name for t in tags if t.tag_kind == "definition"}
    assert "Agent" in defs
    assert "run" in defs
    assert "create_agent" in defs


def test_python_call_reference():
    code = "def main():\n    tool.call()\n    helper()\n"
    tags = extract_symbols_tree_sitter("src/main.py", code)

    refs = {t.symbol_name for t in tags if t.tag_kind == "reference"}
    assert "call" in refs
    assert "helper" in refs


def test_python_line_numbers():
    code = "class Agent:\n    def run(self):\n        pass\n"
    tags = extract_symbols_tree_sitter("src/agent.py", code)

    class_tag = next(t for t in tags if t.symbol_name == "Agent" and t.tag_kind == "definition")
    assert class_tag.line_start == 1

    func_tag = next(t for t in tags if t.symbol_name == "run" and t.tag_kind == "definition")
    assert func_tag.line_start == 2


def test_typescript_export_function():
    code = "export function createAgent(): void {\n  tool.call();\n}\nexport class Agent {}\n"
    tags = extract_symbols_tree_sitter("src/agent.ts", code)

    defs = {t.symbol_name for t in tags if t.tag_kind == "definition"}
    assert "createAgent" in defs
    assert "Agent" in defs

    refs = {t.symbol_name for t in tags if t.tag_kind == "reference"}
    assert "call" in refs


def test_unsupported_language_falls_back_to_regex():
    code = "func main() {\n  fmt.Println(\"hello\")\n}\n"
    tags = extract_symbols_tree_sitter("src/main.go", code)

    assert len(tags) > 0
    assert any(t.symbol_name == "main" for t in tags)


def test_empty_content_returns_empty():
    tags = extract_symbols_tree_sitter("src/empty.py", "")
    assert tags == []
