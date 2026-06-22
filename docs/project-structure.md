# Project Structure

VulnBot uses one LangGraph workflow as its execution path. Modules are grouped by responsibility:

- `actions/`: planning, command generation, and command execution services used by the workflow.
- `benchmarks/`: task adapters, Docker lab lifecycle, non-interactive execution, scoring, and reports.
- `config/`: typed configuration models and YAML settings support.
- `db/`: SQLAlchemy models, repositories, engine creation, and transaction management.
- `docs/`: user documentation, architecture sources, and rendered assets.
- `graph/`: LangGraph state, nodes, routing, and workflow assembly.
- `llm/`: model clients and persisted conversation orchestration.
- `prompts/`: prompt templates for planning and the three penetration-testing roles.
- `rag/`: document parsing, embeddings, retrieval, reranking, and knowledge-base services.
- `roles/`: declarative role definitions for collection, scanning, and exploitation.
- `scripts/`: standalone diagnostics and benchmark command wrappers.
- `server/`: FastAPI application and HTTP routes for knowledge-base operations.
- `tests/`: unit tests for workflow behavior and benchmark adapters.
- `utils/`: small cross-cutting helpers, currently logging only.
- `web/`: Streamlit user interface and its API client.

Root entry points:

- `cli.py`: the only command-line dispatcher.
- `pentest.py`: interactive penetration-test command implementation.
- `startup.py`: API and Web UI process startup.

Runtime-only paths are intentionally excluded from version control:

- `data/`: SQLite data, knowledge-base files, caches, external benchmarks, and optional VM assets.
- `logs/`: application logs.
- `.venv/`: the project Python environment.
- `.python311/`: the local base interpreter currently used by `.venv`.
