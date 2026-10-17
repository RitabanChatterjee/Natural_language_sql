
import json
import os
from typing import TypedDict

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from agent.utils import (
    get_tables,
    get_schema,
    validate_sql,
    execute_sql,
    code_barfer,
)

load_dotenv()

MAX_RETRIES = 3

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
   api_key = os.environ["GROQ_API_KEY"]
)


# ============================================================
# STATE
# ============================================================

class AgentState(TypedDict):
    user_prompt: str
    db_path: str

    visualization_requested: bool
    selected_tables: list[str]
    schema_context: str

    generated_sql: str
    sql_error: str
    sql_attempts: int
    sql_valid: bool
    execution_success: bool

    result_csv_path: str
    generated_code: str
    chart_path: str
    visualization_attempts: int
    visualization_error: str
    visualization_success: bool
    error: str


# ============================================================
# NODE 1: IDENTIFY RELEVANT TABLES + VISUALIZATION INTENT
# ============================================================

def identify_tables(state: AgentState):
    tables = get_tables(state["db_path"])

    response = llm.invoke([
        SystemMessage(content="""
You are a database query planner.

Given a user's question and a list of available tables:

1. Identify ALL tables required to answer the question.
2. Determine whether the user requested a visualization.

Return ONLY a JSON object:

{
    "selected_tables": ["table1", "table2"],
    "visualization_requested": true
}

Do not invent table names.
Do not generate SQL.
"""),
        HumanMessage(content=f"""
User question:
{state["user_prompt"]}

Available tables:
{json.dumps(tables)}
""")
    ])

    # Remove optional Markdown code fences if present.
    content = response.content.strip()

    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]

    result = json.loads(content)

    selected = result["selected_tables"]

    # Never trust the LLM's table selections blindly.
    if not selected or any(table not in tables for table in selected):
        raise ValueError("LLM selected invalid database tables")

    return {
        "selected_tables": selected,
        "visualization_requested": result["visualization_requested"],
    }


# ============================================================
# NODE 2: RETRIEVE SCHEMA
# ============================================================

def retrieve_schema(state: AgentState):
    schema = get_schema(
        state["db_path"],
        state["selected_tables"]
    )

    return {
        "schema_context": schema
    }


# ============================================================
# NODE 3: GENERATE SQL
# ============================================================

def generate_sql(state: AgentState):
    previous_error = state.get("sql_error", "")
    previous_sql = state.get("generated_sql", "")

    response = llm.invoke([
        SystemMessage(content="""
You generate SQLite SELECT queries.

Rules:
- Generate exactly ONE SQL statement.
- Only generate read-only SELECT queries.
- Use only the provided tables and columns.
- Use JOINs when necessary.
- Do not invent columns.
- Do not wrap SQL in Markdown.
- Return SQL only.

If previous SQL and an error are provided, correct the query.
"""),
        HumanMessage(content=f"""
USER QUESTION:
{state["user_prompt"]}

DATABASE SCHEMA:
{state["schema_context"]}

PREVIOUS SQL:
{previous_sql}

PREVIOUS ERROR:
{previous_error}
""")
    ])

    sql = response.content.strip()

    if sql.startswith("```"):
        sql = sql.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    return {
        "generated_sql": sql,
        "sql_attempts": state.get("sql_attempts", 0) + 1,
        "sql_error": "",
        "sql_valid": False,
        "execution_success": False,
    }


# ============================================================
# NODE 4: VALIDATE SQL
# ============================================================

def validate_sql_node(state: AgentState):
    valid, message = validate_sql(state["generated_sql"])

    return {
        "sql_valid": valid,
        "sql_error": "" if valid else message,
        "error": "" if valid else message,
    }


# ============================================================
# NODE 5: EXECUTE SQL
# ============================================================

def execute_sql_node(state: AgentState):
    try:
        execute_sql(
            db_path=state["db_path"],
            sql=state["generated_sql"],
            output_csv=state["result_csv_path"],
        )

        return {
            "execution_success": True,
            "sql_error": "",
            "error": "",
        }

    except Exception as exc:
        return {
            "execution_success": False,
            "sql_error": str(exc),
            "error": str(exc),
        }


# ============================================================
# NODE 6: GENERATE VISUALIZATION CODE
# ============================================================

def generate_visualization(state: AgentState):
    response = llm.invoke([
        SystemMessage(content="""
You are a Python data visualization specialist.

Generate a complete Python script using pandas and matplotlib.

INPUT_CSV and OUTPUT_PNG are already defined in the execution environment.

Requirements:
1. Read INPUT_CSV using pandas.
2. Use the provided database schema to understand column meanings.
3. Use the generated SQL to determine which columns are present
   in the query results, including any aliases or aggregate columns.
4. Do not assume every column in the database schema exists in the CSV.
5. Choose the most appropriate visualization for the user's request.
6. Perform any necessary sorting, formatting or data transformations.
7. Save the final figure to OUTPUT_PNG.
8. Return complete executable Python code only.
9. Do not wrap the code in Markdown.
10. Do not use os, subprocess, shutil, networking or shell commands.

The SQL query has already executed.
You cannot request additional data.
"""),
        HumanMessage(content=f"""
USER REQUEST:
{state["user_prompt"]}

DATABASE SCHEMA:
{state["schema_context"]}

EXECUTED SQL:
{state["generated_sql"]}

CSV RELATIVE PATH:
{state["result_csv_path"]}

OUTPUT IMAGE PATH:
{state["chart_path"]}

Generate the visualization script.
""")
    ])

    code = response.content.strip()

    if code.startswith("```"):
        code = code.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    return {
        "generated_code": code
    }
# ============================================================
# NODE 7: EXECUTE VISUALIZATION
# ============================================================

def execute_visualization(state: AgentState):
    try:
        code_barfer(
            generated_code=state["generated_code"],
            input_csv=state["result_csv_path"],
            output_png=state["chart_path"],
        )

        return {
            "visualization_success": True,
            "visualization_error": "",
            "error": "",
        }

    except Exception as exc:
        return {
            "visualization_success": False,
            "visualization_error": str(exc),
            "error": str(exc),
        }
# ============================================================
# CONDITIONAL EDGES
# ============================================================

def route_validation(state: AgentState):
    if state["sql_valid"]:
        return "execute"

    if state["sql_attempts"] < MAX_RETRIES:
        return "retry"

    return "failed"


def route_execution(state: AgentState):
    if not state["execution_success"]:
        if state["sql_attempts"] < MAX_RETRIES:
            return "retry"

        return "failed"

    if state["visualization_requested"]:
        return "visualize"

    return "display_table"


# ============================================================
# BUILD GRAPH
# ============================================================

builder = StateGraph(AgentState)

# Register nodes
builder.add_node("identify_tables", identify_tables)
builder.add_node("retrieve_schema", retrieve_schema)
builder.add_node("generate_sql", generate_sql)
builder.add_node("validate_sql", validate_sql_node)
builder.add_node("execute_sql", execute_sql_node)
builder.add_node("generate_visualization", generate_visualization)
builder.add_node("execute_visualization", execute_visualization)

# Initial flow
builder.add_edge(START, "identify_tables")
builder.add_edge("identify_tables", "retrieve_schema")
builder.add_edge("retrieve_schema", "generate_sql")
builder.add_edge("generate_sql", "validate_sql")

# SQL validation loop
builder.add_conditional_edges(
    "validate_sql",
    route_validation,
    {
        "execute": "execute_sql",
        "retry": "generate_sql",
        "failed": END,
    }
)

# SQL execution loop + visualization decision
builder.add_conditional_edges(
    "execute_sql",
    route_execution,
    {
        "retry": "generate_sql",
        "failed": END,
        "visualize": "generate_visualization",
        "display_table": END,
    }
)

# Visualization branch
builder.add_edge(
    "generate_visualization",
    "execute_visualization"
)

builder.add_edge("execute_visualization", END)

graph = builder.compile()
