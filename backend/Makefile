.PHONY: install lint format typecheck dev-install pre-commit-install pre-commit-run clean clean-pyinstaller build-binary rebuild-binary

# Install production dependencies
install:
	pip install -r src/backend/requirements.txt
	pip install -r src/servers/requirements.txt

# Install development dependencies
dev-install: install
	pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit-install: dev-install
	pre-commit install

# Run pre-commit on all files
pre-commit-run:
	pre-commit run --all-files

# Run all linting and type checking
lint:
	./scripts/lint.sh

# Auto-format code
format:
	./scripts/format.sh

# Run only type checking
typecheck:
	pyright

# Run only ruff linting
ruff-check:
	ruff check .

# Run only ruff formatting check
ruff-format-check:
	ruff format --check .

# Run all tests
test:
	python -m pytest

# Run unit tests only (skip integration)
test-unit:
	python -m pytest -m "not integration"

# Run integration tests only
test-integration:
	python -m pytest -m integration

# Run tests with coverage
test-coverage:
	python -m pytest --cov=src/backend --cov=src/servers --cov=src/vicoa --cov=src/shared --cov-report=term-missing

# Run specific test file or pattern
# Usage: make test-k ARGS="test_auth"
test-k:
	python -m pytest -k "$(ARGS)"

# Build binary with PyInstaller
build-binary:
	cd pyinstaller && pyinstaller --clean vicoa.spec
	@echo "Binary built at: pyinstaller/dist/vicoa/vicoa"

# Clean and rebuild binary
rebuild-binary: clean-pyinstaller build-binary

# Clean PyInstaller build artifacts
clean-pyinstaller:
	rm -rf pyinstaller/build pyinstaller/dist
	@echo "Cleaned PyInstaller build artifacts"

# Clean all build artifacts
clean: clean-pyinstaller
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache
	@echo "Cleaned all build artifacts"
