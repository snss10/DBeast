# DBeast Setup Guide

Complete guide for configuring DBeast with IDEs, MCP clients, and PostgreSQL connection scenarios.

---

## Table of Contents

- [IDE Configuration](#ide-configuration)
- [Connection Scenarios](#connection-scenarios)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Runtime Connection](#runtime-connection)

---

## IDE Configuration

All IDEs use similar JSON configuration. The main differences are:

- **Config file location**
- **JSON key names** such as `mcpServers` or `mcp.servers`

Use an absolute path to `src/server.py` unless the client supports workspace variables.

### Common Template

```json
{
  "<servers_key>": {
    "dbeast": {
      "command": "python",
      "args": ["/path/to/dbeast/src/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://user:password@host:5432/database"
      }
    }
  }
}
```

### IDE-Specific Setup

| IDE | Config File | Servers Key |
|-----|-------------|-------------|
| **Cursor** | `.mcp.json` project file or `~/.cursor/.mcp.json` global file | `mcpServers` |
| **VS Code** | `.vscode/settings.json` or user `settings.json` | `mcp.servers` |
| **Claude Desktop** | See paths below | `mcpServers` |
| **Windsurf** | `.mcp.json` | `mcpServers` |

### Claude Desktop Config Paths

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### Full Examples

<details>
<summary><b>Cursor / Windsurf (.mcp.json)</b></summary>

```json
{
  "mcpServers": {
    "dbeast": {
      "type": "stdio",
      "command": "python",
      "args": ["C:/path/to/dbeast/src/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://postgres:password@localhost:5432/mydb"
      }
    }
  }
}
```

</details>

<details>
<summary><b>VS Code (.vscode/settings.json)</b></summary>

If VS Code opens the DBeast repository as the workspace root:

```json
{
  "mcp.servers": {
    "dbeast": {
      "command": "python",
      "args": ["${workspaceFolder}/src/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://postgres:password@localhost:5432/mydb"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

```json
{
  "mcpServers": {
    "dbeast": {
      "command": "python",
      "args": ["/path/to/dbeast/src/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://postgres:password@localhost:5432/mydb"
      }
    }
  }
}
```

</details>

---

## Connection Scenarios

Choose your database type and copy the `env` block into your IDE config.

### Local PostgreSQL

```json
"env": {
  "DATABASE_URL": "postgresql://postgres:password@localhost:5432/mydb"
}
```

Or with individual variables:

```json
"env": {
  "DB_HOST": "localhost",
  "DB_PORT": "5432",
  "DB_USER": "postgres",
  "DB_PASSWORD": "password",
  "DB_NAME": "mydb"
}
```

### Docker PostgreSQL

Start the optional local PostgreSQL service:

```bash
docker compose up -d postgres
```

If you use the legacy Compose plugin:

```bash
docker-compose up -d postgres
```

Then configure DBeast:

```json
"env": {
  "DB_HOST": "localhost",
  "DB_PORT": "5432",
  "DB_USER": "postgres",
  "DB_PASSWORD": "postgres",
  "DB_NAME": "testdb",
  "DBEAST_ENABLE_DOCKER_DISCOVERY": "true"
}
```

Use `connect(discover=true)` if you want DBeast to search for a local PostgreSQL container instead of using explicit connection variables.

### AWS RDS Direct

```json
"env": {
  "DATABASE_URL": "postgresql://admin:password@mydb.xxxxx.us-west-2.rds.amazonaws.com:5432/mydb?sslmode=require"
}
```

### AWS RDS Secrets Manager

```json
"env": {
  "AWS_SECRET_NAME": "my-rds-credentials",
  "AWS_REGION": "us-west-2"
}
```

Required secret JSON format:

```json
{
  "host": "mydb.xxxxx.rds.amazonaws.com",
  "port": 5432,
  "username": "admin",
  "password": "secret",
  "dbname": "mydb"
}
```

### AWS RDS SSH Tunnel

Step 1: Start SSH tunnel.

```bash
ssh -L 5432:mydb.xxxxx.rds.amazonaws.com:5432 user@bastion-host -N
```

Step 2: Configure env.

```json
"env": {
  "AWS_SECRET_NAME": "my-rds-credentials",
  "AWS_REGION": "us-west-2",
  "DB_HOST": "localhost",
  "DB_PORT": "5432",
  "DBEAST_SSL_VERIFY": "false"
}
```

`DBEAST_SSL_VERIFY=false` is required because the SSL certificate will not match `localhost`.

### Supabase

Get the connection string from Dashboard -> Settings -> Database:

```json
"env": {
  "DATABASE_URL": "postgresql://postgres.xxxx:[PASSWORD]@aws-0-us-west-1.pooler.supabase.com:6543/postgres?sslmode=require"
}
```

### Neon

Get the connection string from Console -> Connection Details:

```json
"env": {
  "DATABASE_URL": "postgresql://user:password@ep-xxx.us-west-2.aws.neon.tech/mydb?sslmode=require"
}
```

### Railway / Render / Fly.io

Use the connection string from the provider dashboard:

```json
"env": {
  "DATABASE_URL": "postgresql://user:password@host:port/database?sslmode=require"
}
```

---

## Configuration Reference

### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `DBEAST_QUERY_TIMEOUT` | 300s | Query execution timeout |
| `DBEAST_COMMAND_TIMEOUT` | 300s | SQL command timeout |
| `DBEAST_POOL_CONNECTION_TIMEOUT` | 300s | Pool connection acquire timeout |

### Connection Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `DBEAST_POOL_MIN_SIZE` | 1 | Minimum connections |
| `DBEAST_POOL_MAX_SIZE` | 5 | Maximum connections |
| `DBEAST_CONNECTION_MAX_RETRIES` | 5 | Retry attempts |
| `DBEAST_CONNECTION_RETRY_DELAY` | 1.0s | Delay between retries |

### SSL / Security

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_SSLMODE` | prefer | PostgreSQL SSL mode: `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full` |
| `DBEAST_SSL_VERIFY` | true | Verify SSL certificates. Set `false` for SSH tunnels. |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `DBEAST_LOG_LEVEL` | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `DBEAST_LOG_JSON` | false | Emit JSON-formatted logs |

### Audit Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `DBEAST_AUDIT_ENABLED` | true | Enable MCP request/response logging |
| `DBEAST_AUDIT_DIR` | logs/mcp_audit | Directory for audit log files |
| `DBEAST_AUDIT_MAX_RESPONSE_SIZE` | 10000 | Max response chars in logs, truncates if larger |

Logs are stored as daily markdown files with tool calls, parameters with sensitive data masked, responses, and execution times.

### Other

| Variable | Default | Description |
|----------|---------|-------------|
| `DBEAST_DEFAULT_ROW_LIMIT` | 100 | Default max rows returned |
| `DBEAST_SCHEMA_CACHE_TTL` | 60s | Schema cache TTL, set 0 to disable |
| `DBEAST_ENABLE_DOCKER_DISCOVERY` | true | Auto-discover Docker PostgreSQL |

### Impact Analysis Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `DBEAST_MASS_UPDATE_ROWS` | 1000 | Row count threshold for mass UPDATE warnings |
| `DBEAST_MASS_DELETE_ROWS` | 100 | Row count threshold for mass DELETE warnings |
| `DBEAST_DANGEROUS_PERCENT` | 50 | Percentage of table affected to trigger dangerous warnings |
| `DBEAST_CRITICAL_PERCENT` | 90 | Percentage of table affected to trigger critical warnings |

---

## Troubleshooting

### Connection Errors

| Error | Solution |
|-------|----------|
| `connection refused` | Check host/port and ensure PostgreSQL is running |
| `authentication failed` | Verify username and password |
| `database does not exist` | Check database name |
| `SSL certificate verify failed` | Set `DBEAST_SSL_VERIFY=false` for SSH tunnels |
| `timeout expired` | Increase timeout values |

### SSH Tunnel

```bash
ssh -L 5432:rds-endpoint:5432 user@bastion -N
nc -zv localhost 5432
```

Config must use:

```env
DB_HOST=localhost
DBEAST_SSL_VERIFY=false
```

### AWS Secrets Manager

```bash
aws sts get-caller-identity
aws secretsmanager describe-secret --secret-id my-secret
```

Required IAM permission:

```text
secretsmanager:GetSecretValue
```

### Docker Discovery

```bash
docker ps
```

Enable in config:

```env
DBEAST_ENABLE_DOCKER_DISCOVERY=true
```

Then use:

```text
connect(discover=true)
```

### Server Not Starting

Check Python:

```bash
python --version
```

Test from the repository root:

```bash
python src/server.py
```

Check imports after installation:

```bash
pip install -e .
python -c "from src.server import mcp"
```

On Windows, prefer forward slashes in MCP JSON paths:

```json
"args": ["C:/path/to/dbeast/src/server.py"]
```

---

## Runtime Connection

Connect without environment variables:

```text
connect(url='postgresql://user:pass@host:5432/db')
connect(host='localhost', user='postgres', password='secret', database='mydb')
connect(aws_secret_name='my-secret', aws_region='us-west-2')
```

---

## Response Shape

Every MCP tool returns a final JSON wrapper:

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

Formatted responses are also wrapped. Read markdown, text, or Mermaid output from `data.content`:

```json
{
  "success": true,
  "data": {
    "format": "markdown",
    "content": "# Report\n..."
  },
  "meta": {
    "connected": true,
    "source": "tool"
  }
}
```
