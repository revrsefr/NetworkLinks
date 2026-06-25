# NetLink developer quality gate.
#
#   make dev      one-time: create .venv and install tooling + the package (editable)
#   make check    run the full gate: ruff + mypy + pytest  (use this before pushing)
#   make lint / test / typecheck / coverage   run individual checks
#   make install-hooks   install a git pre-commit hook that runs `make check`
#
# CI was removed (Actions billing); this is the local substitute. Keep `make check`
# green -- that's the contract.

VENV   ?= .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
RUFF    := $(VENV)/bin/ruff
PYTEST  := $(VENV)/bin/pytest
MYPY    := $(VENV)/bin/mypy

.PHONY: dev lint test coverage typecheck check install-hooks clean i18n-extract i18n-compile

dev:  ## Create the dev venv and install tooling + the package
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e '.[dev]'
	@echo "✓ dev environment ready in $(VENV)"

lint:  ## Static lint (ruff, config in pyproject.toml)
	$(RUFF) check .

test:  ## Run the test suite
	$(PYTEST) test/ -q

coverage:  ## Test suite with a coverage report
	$(PYTEST) test/ -q --cov=. --cov-report=term:skip-covered

typecheck:  ## Type-check the annotated core (mypy)
	@# package-dir maps the repo root to the `netlink` package, which breaks mypy's
	@# import resolution; expose it under that name via a throwaway symlink.
	@d=$$(mktemp -d) && ln -s "$(CURDIR)" "$$d/netlink" && \
	  MYPYPATH="$$d" $(MYPY) -p netlink; rc=$$?; rm -rf "$$d"; exit $$rc

check: lint typecheck test  ## The full quality gate
	@echo "✓ all checks passed"

install-hooks:  ## Install the git pre-commit hook
	@mkdir -p .git/hooks
	@cp tools/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "✓ installed .git/hooks/pre-commit (bypass a commit with --no-verify)"

i18n-extract:  ## Re-scan the source for translatable strings -> locales/netlink.pot
	xgettext --language=Python --keyword=_ --from-code=UTF-8 --package-name=NetLink \
	  --output=locales/netlink.pot $$(git ls-files '*.py' | grep -v '^test/')

i18n-compile:  ## Compile every .po catalogue to its .mo
	@for po in locales/*/LC_MESSAGES/*.po; do \
	  echo "compiling $$po"; msgfmt "$$po" -o "$${po%.po}.mo"; \
	done

clean:  ## Remove caches and build artifacts
	rm -rf .mypy_cache .pytest_cache .coverage netlink.egg-info build dist
