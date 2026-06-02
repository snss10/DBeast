<div align="center">

<img src="assets/logo.svg" alt="DBeast" width="720" />

**A PostgreSQL MCP server that gives AI assistants expert DBA capabilities.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL 12+](https://img.shields.io/badge/postgresql-12+-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-6e40c9)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)

[Quick Start](#quick-start) · [Demo](#demo) · [Tools](#tools) · [Safety](#safety-model) · [Configuration](#configuration) · [Docs](#documentation)

</div>

---

DBeast connects AI assistants such as Claude, Cursor, Windsurf, and VS Code Copilot to PostgreSQL through the **Model Context Protocol**. Instead of exposing one broad `execute_sql` escape hatch, DBeast provides **21 focused tools** for schema discovery, safe query execution, impact analysis, performance review, security checks, maintenance reporting, replication monitoring, and data quality inspection.

The core guarantee: **write operations are never executed**. `INSERT`, `UPDATE`, `DELETE`, `DROP`, and `TRUNCATE` statements are analyzed and reported as impact previews so your assistant can reason about risky changes without touching live data.

---

## Demo

Watch Claude use DBeast MCP tools to audit a PostgreSQL database, identify security and maintenance risks, and preview cleanup impact without executing destructive SQL.

<div align="center">

[![DBeast MCP demo: Claude audits a PostgreSQL database](https://img.youtube.com/vi/NGfHWBe2CGA/maxresdefault.jpg)](https://youtu.be/NGfHWBe2CGA)

[Watch the demo on YouTube](https://youtu.be/NGfHWBe2CGA)

</div>

---

## How It Works

```text
AI assistant  --MCP stdio-->  DBeast server  --asyncpg-->  PostgreSQL
Claude/Cursor                  Python local                 Local, RDS,
Windsurf/VS Code               subprocess                   Supabase, Neon
```

DBeast runs as a local stdio MCP server. Your IDE or desktop assistant starts it as a subprocess and passes database credentials through environment variables. The assistant calls DBeast tools, DBeast queries PostgreSQL, and structured results come back to the assistant. No HTTP service or extra infrastructure is required.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/snss10/DBeast.git
cd DBeast
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

Optional: copy `.env.example` to `.env` and set your database credentials.

### 2. Verify

```bash
dbeast
```

Or run the source entry point directly:

```bash
python src/server.py
```

### 3. Configure Your MCP Client

Minimal Cursor or Windsurf config:

```json
{
  "mcpServers": {
    "dbeast": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/DBeast/src/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://user:password@localhost:5432/mydb"
      }
    }
  }
}
```

Common config locations:

| Client | Config location |
|---|---|
| Cursor | `.mcp.json` in project root, or `~/.cursor/.mcp.json` globally |
| VS Code | `.vscode/settings.json` or user settings with key `mcp.servers` |
| Claude Desktop on macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop on Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Windsurf | `.mcp.json` |

See [SETUP.md](SETUP.md) for full client examples, Docker, RDS, Supabase, Neon, SSH tunnels, AWS Secrets Manager, and troubleshooting.

### 4. Ask Simple or Complex Questions

Once connected, your assistant can answer quick lookup questions and also run multi-step database investigations.

Simple examples:

```text
Show me the schema for the orders table.
Which queries are slowest right now?
Run a security audit on the public schema.
Generate a Mermaid ERD for the sales schema.
```

More complex examples:

```text
Before I archive old sessions, estimate how many rows would be affected, identify related tables, and tell me the rollback risk.
Investigate why the dashboard query is slow, explain the execution plan, and suggest safe indexes.
Review the public schema for maintenance issues, security risks, and data quality problems, then summarize the top priorities.
Compare table growth, dead tuples, and index health across all schemas and recommend what to vacuum or reindex first.
```

---

## Tools

DBeast exposes 21 MCP tools across 10 categories.

### Connection

| Tool | Description |
|---|---|
| `connect` | Connect to PostgreSQL, check current status, or discover local databases |
| `disconnect` | Close the current database connection |
| `health_check` | Verify connectivity, pool health, PostgreSQL version, and extensions |

### Schema Discovery

| Tool | Description |
|---|---|
| `get_schema` | List schemas, tables, columns, indexes, relationships, and optional Mermaid ERDs |
| `dependency_analysis` | Map object dependencies before renaming, dropping, or changing database objects |

### Data Access

| Tool | Description |
|---|---|
| `execute_query` | Run read-only `SELECT` queries with automatic row-limit injection |

### Query Analysis

| Tool | Description |
|---|---|
| `analyze_query` | Parse and inspect query structure, warnings, and optimization hints |
| `query_optimizer` | Recommend indexes and rewrites for a given query |
| `analyze_impact` | Preview write-query impact, risk level, affected rows, and rollback context without executing |

### Database Health

| Tool | Description |
|---|---|
| `database_health` | Review cache hit rates, connections, transaction age, table health, and overall health signals |
| `query_performance` | Report slow or expensive queries from PostgreSQL statistics |

### Security

| Tool | Description |
|---|---|
| `security_audit` | Inspect roles, privileges, superuser accounts, and public schema exposure |
| `sensitive_data_scan` | Detect likely PII or secrets by column names and schema patterns |

### Maintenance

| Tool | Description |
|---|---|
| `maintenance_analysis` | Review vacuum status, dead tuples, analyze timestamps, and index health |
| `partition_analysis` | Inspect partition health, row distribution, and missing partition risks |

### Data Quality

| Tool | Description |
|---|---|
| `data_quality_report` | Analyze null rates, cardinality, value distributions, and outliers |
| `duplicate_detection` | Find duplicate rows across selected key columns |

### Server Config

| Tool | Description |
|---|---|
| `configuration_review` | Review PostgreSQL configuration and tuning opportunities |
| `replication_status` | Inspect replication lag, WAL sender/receiver state, and replication slots |

### Audit

| Tool | Description |
|---|---|
| `get_audit_logs` | Retrieve logged MCP tool calls for a given date |
| `list_audit_files` | List available audit log files |

---

## Recommended Workflow

Start by discovering schemas:

```text
get_schema()
get_schema(schema='public')
```

Run safe read queries:

```text
execute_query(query='SELECT * FROM orders ORDER BY created_at DESC')
```

Preview risky writes:

```text
analyze_impact(query='DELETE FROM sessions WHERE last_active < now() - interval ''30 days''')
```

Check health and maintenance:

```text
database_health()
maintenance_analysis(schema='public')
query_performance()
```

Most analysis tools accept a `schema` parameter:

```text
maintenance_analysis(schema='public')  -> analyze one schema
maintenance_analysis(schema='all')     -> analyze every schema
get_schema(format='mermaid')           -> generate an ERD diagram
```

---

## Supported Databases

| Provider | Connection method |
|---|---|
| Local PostgreSQL | `DATABASE_URL` or individual `DB_*` variables |
| Docker PostgreSQL | Explicit variables or `connect(discover=true)` |
| AWS RDS / Aurora | Direct URL, SSH tunnel, or AWS Secrets Manager |
| Supabase | Pooler connection string from Dashboard settings |
| Neon | Connection string from Console connection details |
| Railway / Render / Fly.io | Provider connection string |
| Any PostgreSQL host | Standard PostgreSQL URL |

---

## Configuration

Choose one connection method.

```env
# Full URL
DATABASE_URL=postgresql://user:pass@host:5432/db

# Or individual variables
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secret
DB_NAME=mydb
DB_SSLMODE=prefer

# Or AWS Secrets Manager
AWS_SECRET_NAME=my-rds-secret
AWS_REGION=us-west-2
```

You can also connect at runtime:

```text
connect(url='postgresql://user:pass@host:5432/db')
connect(host='localhost', user='postgres', password='secret', database='mydb')
connect(aws_secret_name='my-secret', aws_region='us-west-2')
```

Key settings:

| Variable | Default | Description |
|---|---|---|
| `DBEAST_DEFAULT_ROW_LIMIT` | `100` | Max rows returned by `execute_query` |
| `DBEAST_QUERY_TIMEOUT` | `300` | Query execution timeout in seconds |
| `DBEAST_COMMAND_TIMEOUT` | `300` | SQL command timeout in seconds |
| `DBEAST_SSL_VERIFY` | `true` | Set `false` for SSH tunnels where certificates do not match `localhost` |
| `DBEAST_SCHEMA_CACHE_TTL` | `60` | Schema cache TTL in seconds, `0` disables caching |
| `DBEAST_AUDIT_ENABLED` | `true` | Log MCP tool calls |
| `DBEAST_AUDIT_DIR` | `logs/mcp_audit` | Audit log directory |

See [SETUP.md](SETUP.md) for the complete configuration reference.

---

## Safety Model

| Query type | What DBeast does |
|---|---|
| `SELECT` | Executes with automatic row limits |
| `INSERT` / `UPDATE` / `DELETE` | Never executed; returns an impact preview |
| `DROP` / `TRUNCATE` | Never executed; reports affected objects and risk |

Formatted and JSON responses use a consistent wrapper:

```json
{
  "success": true,
  "data": { "...": "..." },
  "meta": {
    "connected": true,
    "source": "tool"
  }
}
```

---

## Audit Logging

DBeast logs MCP tool calls for accountability and debugging.

```env
DBEAST_AUDIT_ENABLED=true
DBEAST_AUDIT_DIR=logs/mcp_audit
```

Audit files are stored as daily markdown files and include timestamps, tool names, durations, masked parameters, truncated responses, and errors.

---

## Development

```bash
pip install -e ".[dev]"
pre-commit install
pytest tests/ -v
ruff check src/ tests/
ruff format src/ tests/
```

Start the optional local PostgreSQL test database:

```bash
docker compose up -d postgres
```

Legacy Compose:

```bash
docker-compose up -d postgres
```

---

## Documentation

- [SETUP.md](SETUP.md) - Full client setup, connection scenarios, configuration, and troubleshooting
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup, tests, style, commits, and PR process
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Community guidelines

---

## License

MIT
