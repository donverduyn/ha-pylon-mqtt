.PHONY: setup test test-e2e lint format typecheck clean

# Installs from the hash-pinned lock file CI uses, not the loose
# requirements_dev.txt it's compiled from — see .devcontainer/postCreate.sh
# for why that distinction matters. Assumes an already-active venv (the
# devcontainer provides one); run `pre-commit install` once after this to
# get the same checks running locally on every commit.
setup:
	uv pip install --require-hashes -r requirements_dev.lock.txt
	pre-commit install

# Fast suite only (excludes e2e — see [tool.pytest.ini_options] in pyproject.toml).
test:
	pytest

# Spawns real subprocesses (sidecar, Mosquitto, BMS stub); slower, run separately.
test-e2e:
	pytest -m e2e

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .

typecheck:
	mypy
	pyright

clean:
	@bash scripts/clean.sh
