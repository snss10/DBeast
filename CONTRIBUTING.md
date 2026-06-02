# Contributing to DBeast

Thank you for your interest in contributing to DBeast! This document provides guidelines and instructions for contributing.

Please note that this project is released with a [Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 12 or higher (for integration tests)
- Docker (optional, for running tests with containers)

### Setting Up Your Development Environment

1. **Clone the repository**
   ```bash
   git clone https://github.com/ideyalabs/dbeast.git
   cd dbeast
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Set up pre-commit hooks** (optional but recommended)
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Running Tests

### Unit Tests (no database required)

```bash
pytest tests/ -v --ignore=tests/integration/
```

### Integration Tests (requires PostgreSQL)

1. Start a PostgreSQL instance:
   ```bash
   docker-compose up -d postgres
   ```

2. Set the database URL:
   ```bash
   export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/testdb
   ```

3. Run integration tests:
   ```bash
   pytest tests/integration/ -v
   ```

### All Tests with Coverage

```bash
pytest tests/ -v --cov=src --cov-report=html
```

## Code Style

We use the following tools to maintain code quality:

- **Ruff** for linting and formatting
- **mypy** for type checking

### Running Linters

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/

# Type check
mypy src/ --ignore-missing-imports
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write tests for new functionality
   - Update documentation if needed
   - Follow the existing code style

3. **Run tests and linters**
   ```bash
   ruff check src/ tests/
   pytest tests/ -v
   ```

4. **Commit your changes**
   ```bash
   git commit -m "feat: add your feature description"
   ```

   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation
   - `test:` for test changes
   - `refactor:` for refactoring

5. **Push and create a PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Project Structure

```
dbeast/
├── src/
│   ├── core/          # Core infrastructure (logging, config, exceptions)
│   ├── db/            # Database connection and schema discovery
│   ├── middleware/    # Audit logging and middleware
│   ├── models/        # Pydantic models
│   ├── query/         # Query parsing, execution, analysis
│   ├── resources/     # MCP resources
│   ├── services/      # Business logic services
│   ├── tools/         # MCP tool implementations
│   └── utils/         # Utilities and helpers
├── tests/
│   ├── integration/   # Integration tests (DB required)
│   └── *.py           # Unit tests (no DB required)
├── .github/workflows/ # CI/CD pipelines
├── Dockerfile         # Docker configuration
└── docker-compose.yml # Docker Compose for development
```

## Adding a New Tool

1. Create a new file in `src/tools/` or add to an existing file
2. Register the tool in `src/tools/__init__.py`
3. Add tests in `tests/`
4. Update the tool docstring for LLM discoverability
5. Wrap with `@audited()` decorator for audit logging

## Questions?

If you have questions, please open an issue or start a discussion on GitHub.
