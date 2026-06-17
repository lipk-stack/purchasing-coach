# Contributing

Thanks for helping improve Purchasing Coach. This is a deliberately portable,
pure-Python project — please keep the runtime dependency-free (only `openpyxl`)
so the app still runs as a single `.pyz` on locked-down machines.

## Development setup

```bash
pip install -e ".[dev]"     # editable install + pytest, pytest-cov, ruff, python-docx
```

## The loop: lint, test, build

```bash
ruff check .                # lint (config in pyproject.toml)
pytest                      # run the test suite (offline; LLM calls are faked)
pytest --cov=coach          # with coverage
python scripts/build_portable.py   # rebuild dist/purchasing-coach.pyz
```

All three (lint + test matrix on Python 3.10–3.12, and a portable-build
smoke-test) run in CI on every push and pull request
(`.github/workflows/ci.yml`). Please make sure `ruff check .` and `pytest` pass
locally before opening a PR.

## Guidelines

- **Keep the runtime pure-Python.** New backends or formats that need compiled
  or third-party packages go under `[project.optional-dependencies]` and must be
  imported lazily, so the core app keeps working without them.
- **Add tests** for new behaviour and bug fixes; deterministic logic should be
  covered without needing a live model (see `tests/` for the faked-backend
  patterns).
- **Match the surrounding style.** Lint must stay clean; prefer clear, narrow
  exceptions and actionable error messages over bare `except`/`print`.
- **Rebuild the `.pyz`** (`python scripts/build_portable.py`) when you change
  anything under `coach/`, so the committed portable build stays in sync.
- **Samples:** the guideline/template samples are regenerated with
  `python scripts/make_samples.py`.

## Project layout

See the "Project layout" section of [README.md](README.md#development) for a map
of the `coach/` package.
