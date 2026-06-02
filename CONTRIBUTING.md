# Contributing to DBeast

Thank you for your interest in contributing to DBeast. This document explains how to set up a local development environment, run checks, and submit changes.

Please note that this project is released with a [Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project, you agree to abide by its terms.

## Development Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 12 or higher for integration tests
- Docker or Docker Desktop, optional for running a local PostgreSQL container

### Setting Up Your Development Environment

1. **Clone the repository**

   ```bash
   git clone https://github.com/ideyalabs/dbeast.git
   cd dbeast
   ```

2. **Create a virtual environment**

   macOS/Linux:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

   Windows PowerShell:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install development dependencies**

   ```bash
   pip install -e ".[dev]"
   ```

4. **Set up pre-commit hooks** optional but recommended

   ```bash
   pre-commit install
   ```

   To run the same checks on the full repository:

   ```bash
   pre-commit run --all-files
   ```

## Running Tests

### Unit Tests

Unit tests do not require a database:

```bash
pytest tests/ -v --ignore=tests/integration/
```

### Integration Tests

Integration tests require PostgreSQL.

1. Start a PostgreSQL instance:

   ```bash
   docker compose up -d postgres
   ```

   If you use the legacy Compose plugin:

   ```bash
   docker-compose up -d postgres
   ```

2. Set the database URL.

   macOS/Linux:

   ```bash
   export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/testdb
   ```

   Windows PowerShell:

   ```powershell
   $env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/testdb"
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

- **pre-commit** for fast local checks before commits
- **Ruff** for linting and formatting
- **mypy** for type checking

### Running Linters

```bash
pre-commit run --all-files
ruff check src/ tests/
ruff format src/ tests/
mypy src/ --ignore-missing-imports
```

## Pull Request Process

1. **Create a feature branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

   - Write tests for new functionality
   - Update documentation when behavior, setup, or public APIs change
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

### GitHub Push Access

If `git push` returns `Permission denied to <owner>/<repo>.git`, GitHub is authenticating you as an account that does not have write access.

- Use an account with collaborator access to push directly to this repository
- Clear cached GitHub credentials and sign in again if Git is using the wrong account
- Fork the repository and open a pull request if you do not have direct write access

## Project Structure

```text
dbeast/
|-- src/
|   |-- core/          # Core infrastructure: logging, config, exceptions
|   |-- db/            # Database connection and schema discovery
|   |-- middleware/    # Audit logging and middleware
|   |-- models/        # Pydantic models
|   |-- query/         # Query parsing, execution, analysis
|   |-- resources/     # MCP resources
|   |-- services/      # Business logic services
|   |-- tools/         # MCP tool implementations
|   `-- utils/         # Utilities and helpers
|-- tests/
|   |-- integration/   # Integration tests, database required
|   `-- *.py           # Unit tests, no database required
|-- .github/workflows/ # CI/CD pipelines
|-- Dockerfile         # Docker configuration
`-- docker-compose.yml # Docker Compose for development
```

## Adding a New Tool

1. Create a new file in `src/tools/` or add to an existing file.
2. Register the tool in `src/tools/__init__.py`.
3. Add tests in `tests/`.
4. Update the tool docstring for LLM discoverability.
5. Wrap the tool with the `@audited()` decorator for audit logging.
6. Update `README.md` or `SETUP.md` if the tool changes public workflows or configuration.

## Questions?

If you have questions, please open an issue or start a discussion on GitHub.
