# worker.mk is written by the pipeline at instantiation and pins PY to the
# arc-agi-games venv python (absolute path). Fallback: whatever `python` is.
-include worker.mk
PY ?= python

.PHONY: validate scope lint test

validate: scope lint test
	@echo "validate: GREEN"

scope:
	$(PY) tests/check_edit_scope.py

lint:
	$(PY) -m ruff check game.py solver.py

test:
	$(PY) -m pytest -q tests/
