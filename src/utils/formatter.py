"""Rich markdown formatting for Claude Desktop and terminal output."""

from typing import Any


class MarkdownFormatter:
    """Formats data as rich markdown for Claude Desktop."""

    @staticmethod
    def table(headers: list[str], rows: list[list[Any]], max_width: int = 50) -> str:
        """Create a markdown table."""
        if not headers or not rows:
            return "_No data_"

        def truncate(val: Any, width: int) -> str:
            s = str(val) if val is not None else ""
            return s[: width - 3] + "..." if len(s) > width else s

        # Truncate values
        formatted_rows = [[truncate(cell, max_width) for cell in row] for row in rows]

        # Build table
        header_row = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        data_rows = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in formatted_rows]

        return "\n".join([header_row, separator] + data_rows)

    @staticmethod
    def schema_table(table_info: dict) -> str:
        """Format a table schema as markdown."""
        lines = []

        # Table header
        name = f"{table_info.get('schema_name', 'public')}.{table_info['name']}"
        row_count = table_info.get("row_count", 0)
        lines.append(f"### Table: {name}")
        lines.append(f"**Rows:** ~{row_count:,}" if row_count else "**Rows:** unknown")
        lines.append("")

        # Columns table
        columns = table_info.get("columns", [])
        if columns:
            lines.append("#### Columns")
            headers = ["Column", "Type", "Nullable", "Key", "Default"]
            rows = []
            for col in columns:
                pk = "PK" if col.get("is_primary_key") else ""
                nullable = "YES" if col.get("is_nullable") else "NO"
                default = col.get("default", "") or ""
                rows.append(
                    [
                        col["name"],
                        col["data_type"],
                        nullable,
                        pk,
                        default[:30] + "..." if len(str(default)) > 30 else default,
                    ]
                )
            lines.append(MarkdownFormatter.table(headers, rows))
            lines.append("")

        # Foreign keys
        fks = table_info.get("foreign_keys", [])
        if fks:
            lines.append("#### Foreign Keys")
            for fk in fks:
                lines.append(f"- `{fk['column']}` -> `{fk['references_table']}.{fk['references_column']}`")
            lines.append("")

        # Indexes
        indexes = table_info.get("indexes", [])
        if indexes:
            lines.append("#### Indexes")
            for idx in indexes:
                unique = " _(unique)_" if idx.get("is_unique") else ""
                cols = ", ".join(idx.get("columns", []))
                lines.append(f"- `{idx['name']}`: ({cols}){unique}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def query_result(result: dict) -> str:
        """Format query result as markdown."""
        lines = []

        query = result.get("query", "")
        row_count = result.get("row_count", 0)
        exec_time = result.get("execution_time_ms", 0)
        columns = result.get("columns", [])
        rows = result.get("rows", [])

        # Header
        lines.append("### Query Result")
        lines.append("")
        lines.append(f"**Rows returned:** {row_count} | **Execution time:** {exec_time}ms")
        lines.append("")

        # Query
        lines.append("<details>")
        lines.append("<summary>Query</summary>")
        lines.append("")
        lines.append("```sql")
        lines.append(query)
        lines.append("```")
        lines.append("</details>")
        lines.append("")

        # Results table
        if rows:
            data_rows = [[row.get(col, "") for col in columns] for row in rows]
            lines.append(MarkdownFormatter.table(columns, data_rows))
        else:
            lines.append("_No rows returned_")

        return "\n".join(lines)

    @staticmethod
    def query_analysis(analysis: dict) -> str:
        """Format query analysis as markdown."""
        lines = []

        valid = analysis.get("valid", False)
        query_type = analysis.get("query_type", "UNKNOWN")

        # Status header
        status = "[VALID]" if valid else "[INVALID]"
        lines.append(f"### Query Analysis - {status}")
        lines.append("")

        if not valid:
            error = analysis.get("error", "Unknown error")
            lines.append(f"**Error:** {error}")
            return "\n".join(lines)

        lines.append(f"**Type:** `{query_type}`")
        lines.append("")

        # Tables and columns
        tables = analysis.get("tables", [])
        columns = analysis.get("columns", [])

        if tables:
            lines.append(f"**Tables:** {', '.join(f'`{t}`' for t in tables)}")
        if columns:
            col_list = columns[:10]
            more = f" _+{len(columns) - 10} more_" if len(columns) > 10 else ""
            lines.append(f"**Columns:** {', '.join(f'`{c}`' for c in col_list)}{more}")
        lines.append("")

        # Joins
        joins = analysis.get("joins", [])
        if joins:
            lines.append("**Joins:**")
            for j in joins:
                cond = f" ON `{j.get('condition')}`" if j.get("condition") else ""
                lines.append(f"- `{j['join_type']}` `{j['table']}`{cond}")
            lines.append("")

        # Warnings
        warnings = analysis.get("warnings", [])
        if warnings:
            lines.append("#### Warnings")
            for w in warnings:
                lines.append(f"- {w}")
            lines.append("")

        # Suggestions
        suggestions = analysis.get("suggestions", [])
        if suggestions:
            lines.append("#### Suggestions")
            for s in suggestions:
                lines.append(f"- {s}")
            lines.append("")

        # Formatted query
        formatted = analysis.get("formatted_query", "")
        if formatted:
            lines.append("<details>")
            lines.append("<summary>Formatted Query</summary>")
            lines.append("")
            lines.append("```sql")
            lines.append(formatted)
            lines.append("```")
            lines.append("</details>")

        return "\n".join(lines)

    @staticmethod
    def impact_preview(preview: dict) -> str:
        """Format impact preview as markdown."""
        lines = []

        query_type = preview.get("query_type", "UNKNOWN")
        target = preview.get("target_table", "unknown")
        affected = preview.get("affected_rows", 0)
        warning = preview.get("warning")
        sample_rows = preview.get("sample_rows", [])
        cascade_info = preview.get("cascade_info", [])

        # Header with severity indicator
        if affected > 1000:
            severity = "[HIGH IMPACT]"
        elif affected > 100:
            severity = "[MEDIUM IMPACT]"
        else:
            severity = "[LOW IMPACT]"

        lines.append(f"### Impact Preview - {query_type} {severity}")
        lines.append("")

        lines.append(f"**Target:** `{target}`")
        lines.append(f"**Affected Rows:** {affected:,}")
        lines.append("")

        # Warning banner
        if warning:
            lines.append(f"> **WARNING:** {warning}")
            lines.append("")

        # Sample data
        if sample_rows:
            lines.append("#### Sample Data (will be affected)")
            columns = list(sample_rows[0].keys()) if sample_rows else []
            rows = [[row.get(col, "") for col in columns] for row in sample_rows[:5]]
            lines.append(MarkdownFormatter.table(columns, rows))
            if len(sample_rows) > 5:
                lines.append(f"_...and {len(sample_rows) - 5} more rows_")
            lines.append("")

        # Cascade effects
        if cascade_info:
            lines.append("#### Cascade Effects")
            for cascade in cascade_info:
                table = cascade.get("table", "unknown")
                on_delete = cascade.get("on_delete", "NO ACTION")
                potential = cascade.get("potential_cascade_rows", 0)

                if on_delete == "CASCADE":
                    lines.append(f"- `{table}`: **{potential:,} rows** will be deleted (CASCADE)")
                else:
                    lines.append(f"- `{table}`: {on_delete}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def connection_status(status: dict) -> str:
        """Format connection status as markdown."""
        lines = []

        is_connected = status.get("status") == "connected"
        state = "[CONNECTED]" if is_connected else "[DISCONNECTED]"

        lines.append(f"### Connection Status {state}")
        lines.append("")

        if is_connected:
            lines.append(f"**Host:** `{status.get('host')}:{status.get('port')}`")
            lines.append(f"**Database:** `{status.get('database')}`")
            lines.append(f"**User:** `{status.get('user')}`")
            lines.append(f"**SSL:** {'Enabled' if status.get('ssl') else 'Disabled'}")
            if status.get("aws_secret"):
                lines.append(f"**AWS Secret:** `{status.get('aws_secret')}`")
            if status.get("version"):
                version = str(status.get("version"))
                lines.append(f"**Version:** {version[:50]}...")
        else:
            error = status.get("error", "Not connected")
            lines.append(f"**Status:** {error}")

        return "\n".join(lines)

    @staticmethod
    def mermaid_erd(tables: list[dict]) -> str:
        """Generate Mermaid ERD diagram from schema."""
        lines = ["```mermaid", "erDiagram"]

        # Define tables
        for table in tables:
            table_name = table["name"]
            lines.append(f"    {table_name} {{")

            for col in table.get("columns", [])[:10]:  # Limit columns
                col_type = col["data_type"].replace(" ", "_")
                pk = "PK" if col.get("is_primary_key") else ""
                lines.append(f"        {col_type} {col['name']} {pk}")

            lines.append("    }")

        # Define relationships
        for table in tables:
            table_name = table["name"]
            for fk in table.get("foreign_keys", []):
                ref_table = fk["references_table"]
                lines.append(f'    {ref_table} ||--o{{ {table_name} : "has"')

        lines.append("```")
        return "\n".join(lines)
