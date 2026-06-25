from agenttrace.agents.analysis.config_parser import parse_config_file


def test_parse_package_json():
    content = '{"dependencies": {"express": "^4.0"}, "scripts": {"start": "node index.js"}, "main": "index.js"}'
    result = parse_config_file("package.json", content)
    assert result["type"] == "package.json"
    assert "express" in result["dependencies"]
    assert "start" in result["scripts"]
    assert result["entrypoint"] == "index.js"


def test_parse_dockerfile():
    content = "FROM node:18\nRUN npm install\nCMD [\"node\", \"index.js\"]\n"
    result = parse_config_file("Dockerfile", content)
    assert result["type"] == "dockerfile"
    assert "node:18" in result["base_images"]
    assert len(result["commands"]) > 0


def test_parse_pyproject_toml():
    content = '[project]\ndependencies = [\n    "langgraph>=0.6",\n    "httpx>=0.28",\n]\n'
    result = parse_config_file("pyproject.toml", content)
    assert result["type"] == "pyproject.toml"
    assert "langgraph" in result["dependencies"]


def test_unsupported_file_returns_empty():
    result = parse_config_file("src/main.py", "def main(): pass")
    assert result == {}
