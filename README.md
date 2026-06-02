# DBeast


              ██████╗ ██████╗ ███████╗ █████╗ ███████╗████████╗
              ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔════╝╚══██╔══╝
              ██║  ██║██████╔╝█████╗  ███████║███████╗   ██║
              ██║  ██║██╔══██╗██╔══╝  ██╔══██║╚════██║   ██║
              ██████╔╝██████╔╝███████╗██║  ██║███████║   ██║
              ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝   ╚═╝

      Expert-level PostgreSQL database analysis MCP server for AI assistants.

## Features

- **Schema Discovery** - Tables, columns, relationships, indexes, ERD diagrams
- **Query Execution** - Run SELECT queries safely with automatic LIMIT injection
- **Impact Analysis** - Preview UPDATE/DELETE/DROP effects before execution
- **Performance Analysis** - Execution plans, index recommendations, health metrics
- **Security Audits** - Role analysis, privilege checks, sensitive data detection
- **Maintenance Analysis** - Vacuum status, bloat detection, index health
- **Replication Monitoring** - Lag detection, slot health, WAL analysis
- **Data Quality** - Null analysis, duplicate detection, outlier detection
- **Safe by Design** - Write queries are never executed, only analyzed

## Supported Databases

- Local PostgreSQL
- AWS RDS / Aurora
- Supabase
- Neon
- Railway / Render / Fly.io
- Docker containers
- Any PostgreSQL via SSH tunnel

---

## Requirements

- Python 3.11+
- PostgreSQL 12+ (target database)

---

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Configure IDE

See **[SETUP.md](SETUP.md)** for detailed IDE configuration (Cursor, VS Code, Claude Desktop).

**Minimal Cursor config** (`.mcp.json`):
```json
{
  "mcpServers": {
    "dbeast": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/dbeast/src/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://user:password@localhost:5432/mydb"
      }
    }
  }
}
```

### 3. Use

```
1. get_schema()                    → Discover tables and schemas
2. get_schema(schema='sales')      → View tables in a schema
3. execute_query(query='SELECT..') → Run queries
4. maintenance_analysis(schema='sales') → Check index/vacuum health
```

---

## Available Tools (21)

| Category | Tools |
|----------|-------|
| **Connection** | `connect`, `disconnect`, `health_check` |
| **Server Config** | `configuration_review`, `replication_status` |
| **Database Health** | `database_health`, `query_performance` |
| **Schema Discovery** | `get_schema`, `dependency_analysis` |
| **Security** | `security_audit`, `sensitive_data_scan` |
| **Maintenance** | `maintenance_analysis`, `partition_analysis` |
| **Data Quality** | `data_quality_report`, `duplicate_detection` |
| **Query Analysis** | `analyze_query`, `query_optimizer`, `analyze_impact` |
| **Data Access** | `execute_query` |
| **Audit** | `get_audit_logs`, `list_audit_files` |

---

## Schema Parameter

**Important:** Most tools require explicit schema specification.

```
get_schema()                           → Lists all schemas (discovery)
maintenance_analysis()                 → Prompts for schema selection
maintenance_analysis(schema='sales')   → Analyzes 'sales' schema
maintenance_analysis(schema='all')     → Analyzes ALL schemas
```

**Workflow:** Always call `get_schema()` first to discover available schemas.

---

## Output Formats

| Format | Description |
|--------|-------------|
| `json` | Structured data (default) |
| `markdown` | Human-readable tables |
| `mermaid` | ERD diagrams (`get_schema` only) |

---

## Safety Model

| Query Type | Behavior |
|------------|----------|
| **SELECT** | Executed with auto-LIMIT |
| **INSERT/UPDATE/DELETE** | Never executed, only analyzed |
| **DROP/TRUNCATE** | Never executed, shows impact |

---

## Configuration

### Environment Variables

```env
# Connection (choose one)
DATABASE_URL=postgresql://user:pass@host:5432/db
# OR
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secret
DB_NAME=mydb
DB_SSLMODE=prefer
# OR
AWS_SECRET_NAME=my-secret
AWS_REGION=us-west-2

# Timeouts (defaults: 5 minutes)
DBEAST_QUERY_TIMEOUT=300
DBEAST_COMMAND_TIMEOUT=300
DBEAST_POOL_CONNECTION_TIMEOUT=300

# SSL
DBEAST_SSL_VERIFY=true  # Set 'false' for SSH tunnels
```

See **[SETUP.md](SETUP.md)** for complete configuration reference.

---

## Response Format

All MCP tool responses use the same final wrapper shape.

### Success
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "connected": true,
    "source": "tool"
  }
}
```

### Formatted Output

When `format='markdown'`, `format='text'`, or `format='mermaid'` is requested, the formatted content is wrapped under `data.content`:

```json
{
  "success": true,
  "data": {
    "format": "markdown",
    "content": "### Query Result\n..."
  },
  "meta": {
    "connected": true,
    "source": "tool"
  }
}
```

### Error
```json
{
  "success": false,
  "error": {
    "code": "NOT_CONNECTED",
    "message": "Not connected to database",
    "hint": "Use connect() or pass 'url' parameter"
  },
  "meta": {
    "connected": false,
    "source": "tool"
  }
}
```

---

## Audit Logging

All MCP tool calls are logged for accountability and debugging:

```bash
# Configuration
DBEAST_AUDIT_ENABLED=true        # Enable/disable (default: true)
DBEAST_AUDIT_DIR=logs/mcp_audit  # Log directory
```

Logs are stored as daily markdown files (`2026-05-29.md`) containing:
- Timestamp, tool name, duration
- Request parameters (sensitive data masked)
- Response (truncated if large)
- Errors (if any)

**Tools:**
- `get_audit_logs(date='2026-05-29', limit=50)` - Retrieve logs
- `list_audit_files()` - List available log files

---

## Documentation

- **[SETUP.md](SETUP.md)** - Installation, configuration, and troubleshooting
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - How to contribute, develop, test, and submit changes
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** - Community guidelines and expected conduct

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Optional: install git hooks
pre-commit install

# Run tests
pytest tests/ -v

# Lint
ruff check src/
ruff format src/
```

---

## License

MIT
