# Contributing to Digital Twin Road

Thank you for your interest in contributing to **Digital Twin Road**!

## Prerequisites

- **Python:** `3.11`, `3.12`, or `3.13`
- **Node.js:** `>= 20.x` (Node `22.x` recommended)
- **Optional:** Docker & Docker Compose for containerized stack verification, Zensical (`zensical`, `pymdown-extensions`) for building documentation via `./manage.sh docs`.

## Development Setup

```bash
# 1. Install Python dependencies (plus pytest and ruff for development)
pip install -r requirements.txt pytest ruff

# 2. Install frontend dependencies
cd frontend && npm ci --legacy-peer-deps && cd ..

# 3. Launch local dev servers (FastAPI :8000 + Vite :5173 with HMR)
./manage.sh up-local

# 4. Stop local dev servers
./manage.sh down-local
```

## Verification Gates

Before opening a pull request, ensure all checks pass locally:

```bash
# Backend linter
ruff check .

# Backend test suite (must not mutate tracked scenarios/ or configs/ files)
pytest -v

# Frontend TypeScript check & production build
cd frontend && npm run build

# Or run the combined test & build gate via the CLI orchestrator
./manage.sh test
```

## Coding & Contribution Guidelines

- **Keep tests hermetic:** Never write runtime artifacts or test mutations into tracked files under `scenarios/` or `configs/`. Use `tmp_path` and `monkeypatch`.
- **Clean code & typing:** Follow the Ruff rules configured in `pyproject.toml` (`E`, `F`, `W`, `B`) and keep TypeScript checks (`vue-tsc -b`) warning- and error-free.
- **Documentation:** Update `README.md`, `CHANGELOG.md`, or `docs/` if your change alters endpoints, configuration schemas, or CLI workflows.
- **Commit style:** Use clear, descriptive commit messages (e.g., `feat(hpn): ...`, `fix(world): ...`, `test(api): ...`, `docs: ...`).
