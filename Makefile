.PHONY: dev-api test

dev-api:
	.venv/bin/python -m uvicorn agenttrace.app.main:app --app-dir src --host 127.0.0.1 --port 8000

test:
	.venv/bin/python -m pytest
