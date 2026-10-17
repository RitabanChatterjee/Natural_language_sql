"""Deterministic helpers for QueryCanvas.

Requires: pandas, sqlglot, matplotlib. Generated plotting code runs locally
WITHOUT a security sandbox; use only with trusted/local prototyping.
No query rows are returned to LLMs.
"""
from __future__ import annotations

import csv
import re
import os
import sys
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import sqlglot
from sqlglot import exp


PLOT_TIMEOUT_SECONDS = 30
SQL_TIMEOUT_SECONDS = 15
MAX_RESULT_ROWS = 100_000


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _readonly_connection(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve(strict=True)
    # URI escaping is handled by Path.as_uri(). SQLite understands file: URIs.
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA query_only = ON")
    return conn


def get_tables(db_path: str | Path) -> list[str]:
    with _readonly_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]


def get_schema(db_path: str | Path, tables: list[str]) -> str:
    """Return selected schemas, including PK and FK metadata; no result rows."""
    available = set(get_tables(db_path))
    if not tables or any(table not in available for table in tables):
        raise ValueError("One or more selected tables do not exist")

    sections = []
    with _readonly_connection(db_path) as conn:
        for table in dict.fromkeys(tables):
            quoted = _quote_identifier(table)
            cols = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            fks = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
            lines = [f"TABLE {table}:", "COLUMNS:"]
            for _, name, dtype, not_null, default, pk in cols:
                lines.append(
                    f"- {name}: {dtype or 'ANY'}"
                    + (" PRIMARY KEY" if pk else "")
                    + (" NOT NULL" if not_null else "")
                )
            lines.append("FOREIGN KEYS:")
            for _, _, target, source_col, target_col, *_ in fks:
                lines.append(f"- {source_col} -> {target}.{target_col}")
            if not fks:
                lines.append("- none declared")
            sections.append("\n".join(lines))
    return "\n\n".join(sections)


def validate_sql(sql: str) -> tuple[bool, str]:
    """Allow one SQLite SELECT statement (including WITH ... SELECT)."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError) as exc:
        return False, f"SQL parse error: {exc}"

    if len(statements) != 1:
        return False, "Exactly one SQL statement is required"
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        return False, "Only SELECT statements are permitted"

    # Reject command-like constructs anywhere in the AST, including nested ones.
    forbidden_names = (
        "Insert", "Update", "Delete", "Drop", "Alter", "Create", "Command",
        "Attach", "Detach", "Pragma", "Transaction", "Commit", "Rollback",
        "Merge", "Copy", "Into", "LoadData", "Set", "Use", "Grant", "Revoke",
    )
    forbidden = tuple(
        cls for name in forbidden_names
        if (cls := getattr(exp, name, None)) is not None
    )
    for node in tree.walk():
        if isinstance(node, forbidden):
            return False, f"Forbidden SQL construct: {type(node).__name__}"

    # SQLite permits SELECT load_extension(...) in some configurations. Restrict
    # functions rather than assuming a SELECT can never have side effects.
    for node in tree.walk():
        if isinstance(node, exp.Func):
            func_name = node.sql_name().lower() if hasattr(node, "sql_name") else ""
            if func_name in {"load_extension", "writefile", "readfile"}:
                return False, f"Forbidden SQL function: {func_name}"
    return True, "Valid read-only SELECT"



import os
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd


def execute_sql(
    db_path: str,
    sql: str,
    output_csv: str
) -> None:

    output_path = Path(output_csv).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a temporary filename, then immediately close its
    # Windows file handle before pandas tries to write to it.
    fd, temp_path = tempfile.mkstemp(
        prefix=".result_",
        suffix=".csv",
        dir=output_path.parent
    )
    os.close(fd)

    try:
        # Defence in depth: validate before execution.
        valid, error = validate_sql(sql)
        if not valid:
            raise ValueError(error)

        db_uri = Path(db_path).resolve().as_uri() + "?mode=ro"

        with sqlite3.connect(db_uri, uri=True) as conn:
            conn.execute("PRAGMA query_only = ON")

            # Write query results directly to the temporary CSV.
            # No results are returned to LangGraph or the LLM.
            with open(temp_path, "w", newline="", encoding="utf-8") as file:
                first_chunk = True

                for chunk in pd.read_sql_query(
                    sql,
                    conn,
                    chunksize=5000
                ):
                    chunk.to_csv(
                        file,
                        index=False,
                        header=first_chunk
                    )
                    first_chunk = False

        # All file handles have now been closed.
        os.replace(temp_path, output_path)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def ingest_csv(csv_path: str | Path, db_path: str | Path, table_name: str) -> None:
    """Import a trusted uploaded CSV into a SQLite table; creates/replaces table."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("Table name must contain only letters, digits and underscores")
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        # pandas handles the CSV ingestion; the SQL-query connection remains read-only.
        for chunk_index, chunk in enumerate(pd.read_csv(csv_path, chunksize=5000)):
            chunk.to_sql(table_name, conn, if_exists="replace" if chunk_index == 0 else "append", index=False)



import subprocess
import sys
from pathlib import Path


def code_barfer(
    generated_code: str,
    input_csv: str,
    output_png: str
):
    # utils.py is in the project root.
    BASE_DIR = Path(__file__).resolve().parent

    # Permanent debugging directory.
    DEBUG_DIR = BASE_DIR / "generated"
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    script_path = DEBUG_DIR / "empty_gen.py"

    input_csv = Path(input_csv).resolve()
    output_png = Path(output_png).resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    # Write exactly what the LLM generated, preceded only
    # by the two path variables it needs.
    script = (
        f"INPUT_CSV = {str(input_csv)!r}\n"
        f"OUTPUT_PNG = {str(output_png)!r}\n\n"
        + generated_code
    )

    script_path.write_text(script, encoding="utf-8")

    print(f"\nGenerated Python saved to: {script_path}")

    # Check syntax before executing.
    try:
        compile(script, str(script_path), "exec")
    except SyntaxError as exc:
        raise RuntimeError(
            f"Generated Python has a syntax error at line "
            f"{exc.lineno}: {exc.msg}\n"
            f"Inspect: {script_path}"
        ) from exc

    # Execute the generated script.
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=DEBUG_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Visualization failed:\n{result.stderr}\n\n"
            f"Generated code saved at: {script_path}"
        )

    if not output_png.is_file():
        raise RuntimeError(
            f"Visualization script did not produce a PNG.\n"
            f"Inspect: {script_path}"
        )

    return str(output_png)
