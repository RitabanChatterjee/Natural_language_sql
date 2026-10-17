"""QueryCanvas Streamlit UI. Run: streamlit run app.py"""
from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from agent.graph import graph
from agent.utils import get_tables, ingest_csv

st.set_page_config(page_title="QueryCanvas", page_icon="📊", layout="wide")
st.title("QueryCanvas")
st.caption("Upload CSV files or a SQLite database, then ask questions in natural language.")


def workspace() -> Path:
    if "workspace" not in st.session_state:
        st.session_state.workspace = tempfile.TemporaryDirectory(prefix="querycanvas_")
    return Path(st.session_state.workspace.name)


def safe_table_name(filename: str) -> str:
    name = re.sub(r"\W+", "_", Path(filename).stem).strip("_")
    if not name or name[0].isdigit():
        name = "table_" + name
    return name


def load_uploads(files) -> None:
    root = workspace()
    db_path = root / "data.db"
    # Build a new DB per upload action, not per Streamlit rerun.
    db_path.unlink(missing_ok=True)
    sqlite_files = [f for f in files if Path(f.name).suffix.lower() in {".db", ".sqlite", ".sqlite3"}]
    csv_files = [f for f in files if Path(f.name).suffix.lower() == ".csv"]
    if len(sqlite_files) > 1 or (sqlite_files and csv_files):
        raise ValueError("Upload either one SQLite database or one/more CSV files, not both.")
    if sqlite_files:
        db_path.write_bytes(sqlite_files[0].getvalue())
        # Validate that this is actually a readable SQLite database.
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA schema_version").fetchone()
    else:
        used = set()
        for idx, uploaded in enumerate(csv_files):
            table = safe_table_name(uploaded.name)
            if table.lower() in used:
                table = f"{table}_{idx + 1}"
            used.add(table.lower())
            source = root / f"upload_{idx}.csv"
            source.write_bytes(uploaded.getvalue())
            ingest_csv(source, db_path, table)
            source.unlink(missing_ok=True)
    tables = get_tables(db_path)
    if not tables:
        raise ValueError("No queryable tables found in the uploaded data.")
    st.session_state.db_path = str(db_path)
    st.session_state.tables = tables
    st.session_state.pop("last_result", None)


files = st.file_uploader(
    "Upload data",
    type=["csv", "db", "sqlite", "sqlite3"],
    accept_multiple_files=True,
    help="Upload one SQLite database, or multiple CSV files (each becomes a table).",
)
if st.button("Load data", disabled=not files):
    try:
        load_uploads(files)
        st.success("Data loaded successfully.")
    except Exception as exc:
        st.session_state.pop("db_path", None)
        st.error(f"Could not load data: {exc}")

if "db_path" in st.session_state:
    st.write("**Available tables:**", ", ".join(st.session_state.tables))
    with st.form("question_form"):
        question = st.text_area(
            "Ask a question about your data",
            placeholder="Which department has the highest average salary? Show it as a bar chart.",
        )
        submitted = st.form_submit_button("Run analysis", type="primary")

    if submitted:
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            root = workspace()
            result_csv = root / "result.csv"
            chart_png = root / "chart.png"
            result_csv.unlink(missing_ok=True)
            chart_png.unlink(missing_ok=True)
            initial_state = {
                "user_prompt": question.strip(),
                "db_path": st.session_state.db_path,
                "visualization_requested": False,
                "selected_tables": [],
                "schema_context": "",
                "generated_sql": "",
                "sql_error": "",
                "sql_attempts": 0,
                "visualization_attempts": 0,
"visualization_error": "",
"visualization_success": False,
                "sql_valid": False,
                "execution_success": False,
                "result_csv_path": str(result_csv),
                "generated_code": "",
                "chart_path": str(chart_png),
                "error": "",
            }
            try:
                with st.spinner("Analysing your data..."):
                    result = graph.invoke(initial_state, config={"recursion_limit": 25})
                st.session_state.last_result = result
            except Exception as exc:
                st.session_state.pop("last_result", None)
                st.error(f"Analysis failed: {exc}")

    if "last_result" in st.session_state:
        result = st.session_state.last_result
        if result.get("error"):
            st.error(result["error"])
        else:
            with st.expander("Generated SQL", expanded=False):
                st.code(result.get("generated_sql", ""), language="sql")
            csv_path = Path(result["result_csv_path"])
            if result.get("visualization_requested"):
                chart = Path(result["chart_path"])
                if chart.is_file():
                    st.image(str(chart), caption="Generated visualization", use_container_width=True)
                    st.download_button("Download chart", chart.read_bytes(), "chart.png", "image/png")
                else:
                    st.error("The visualization file was not created.")
            elif csv_path.is_file():
                df = pd.read_csv(csv_path)
                st.dataframe(df, use_container_width=True)
                st.download_button("Download result CSV", csv_path.read_bytes(), "result.csv", "text/csv")
            else:
                st.error("The result CSV was not created.")
