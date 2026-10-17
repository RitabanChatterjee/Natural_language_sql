# QueryCanvas

### Ask questions about your data in natural language.

QueryCanvas is an LLM-powered data analysis application that allows users to upload CSV files or SQLite databases, ask questions in plain English, and receive SQL-backed answers as interactive tables or generated visualisations.

Built using **LangGraph, Groq, SQLite, Pandas, Matplotlib and Streamlit**, QueryCanvas uses a multi-stage agent workflow to identify relevant tables, generate and validate SQL, execute queries, and produce visualisations.

## Features

- **Natural Language to SQL:** Ask questions without writing SQL manually.
- **CSV and SQLite Support:** Upload CSV datasets or existing SQLite databases.
- **Intelligent Table Selection:** An LLM identifies the relevant tables for each query.
- **Schema-Aware SQL Generation:** Queries are generated using database schemas and table relationships.
- **SQL Validation:** Generated queries undergo syntax and safety checks before execution.
- **Automatic Error Correction:** Failed SQL queries are regenerated using validation or execution errors.
- **Dynamic Visualisations:** Generate Matplotlib charts based on natural-language requests.
- **Visualisation Retry Loop:** Failed plotting scripts are corrected using their execution errors.
- **Interactive Results:** View query results using Streamlit's DataFrame interface.
- **Read-Only Queries:** Database queries execute through read-only SQLite connections.

## Architecture

QueryCanvas separates LLM-driven decision-making from deterministic database operations.

```text
                   User Prompt
                        |
                        v
             Identify Relevant Tables
             + Visualisation Intent
                        |
                        v
                Retrieve Schemas
                        |
                        v
                   Generate SQL <--------+
                        |                |
                        v                |
                  Validate SQL           |
                        |                |
                 Invalid / Error --------+
                        |
                      Valid
                        |
                        v
                   Execute SQL <---------+
                        |                |
                   SQL Error ------------+
                        |
                     Success
                        |
                        v
                   result.csv
                        |
                +-------+-------+
                |               |
          Table Requested  Chart Requested
                |               |
                v               v
          Pandas Display   Generate Python <----+
                                |                |
                                v                |
                          Execute Script         |
                                |                |
                           Error / Retry --------+
                                |
                              Success
                                |
                                v
                            chart.png
```

SQL generation and visualisation generation each support up to three attempts.

**Query results are never sent to the LLM.** They are written directly to `result.csv`. The visualisation agent receives the user request, schema context, executed SQL and CSV path—not the actual query-result rows.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Core application |
| LangGraph | Agent orchestration and conditional workflows |
| Groq | Hosted LLM inference |
| SQLite | Database storage and query execution |
| SQLGlot | SQL parsing and validation |
| Pandas | CSV ingestion and result handling |
| Matplotlib | Data visualisation |
| Streamlit | Web interface |
| Pydantic | Structured data validation |

## Project Structure

```text
querycanvas/
│
├── app.py                  # Streamlit frontend
├── utils.py                # Database and execution utilities
├── requirements.txt        # Python dependencies
├── .gitignore
│
├── agents/
│   ├── __init__.py
│   └── graph.py            # LangGraph workflow
│
└── generated/
    ├── result.csv          # Temporary SQL output
    ├── empty_gen.py        # Generated plotting script
    └── chart.png           # Generated visualisation
```

Generated artifacts are runtime files and should not be committed to Git.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/RitabanChatterjee/Natural_language_sql
cd Natural_language_sql
```

### 2. Create a virtual environment

On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure Groq

Create an API key at [Groq Console](https://console.groq.com/keys).

In PowerShell:

```powershell
$env:GROQ_API_KEY = "your_api_key_here"
```

Alternatively, create a `.env` file in the project root:

```env
GROQ_API_KEY=your_api_key_here
```

Never commit your API key to GitHub.

### 5. Run the application

```bash
python -m streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## Usage

1. Upload one or more CSV files or an existing SQLite database.
2. Enter a question about your data.
3. QueryCanvas identifies the relevant tables and generates SQL.
4. The SQL is validated, corrected if necessary, and executed.
5. Results appear as an interactive table or generated visualisation.

### Example Queries

**Data retrieval**

- Show the ten highest-rated restaurants.
- What is the average salary by department?
- Which products generated the most revenue?
- Find all restaurants serving Italian cuisine.

**Visualisations**

- Generate a bar chart showing average salary by department.
- Plot monthly revenue as a line graph.
- Show the relationship between restaurant ratings and prices.
- Create a pie chart showing sales distribution by category.

## Agent Workflow

The LangGraph workflow consists of the following nodes:

| Node | Responsibility |
|---|---|
| `identify_tables` | Select relevant tables and classify visualisation intent |
| `retrieve_schema` | Retrieve selected database schemas |
| `generate_sql` | Generate or correct SQL |
| `validate_sql` | Validate generated SQL |
| `execute_sql` | Execute SQL and export results |
| `generate_visualization` | Generate or correct plotting code |
| `execute_visualization` | Execute plotting code and produce an image |

Conditional edges handle SQL retries, execution failures and visualisation retries.

## Security Considerations

QueryCanvas uses SQL validation and read-only SQLite connections to reduce the risk of destructive database operations.

**Important:** The current prototype executes LLM-generated visualisation code locally using a subprocess. This is not a security sandbox. Generated code can potentially access resources available to the application process.

The current implementation is intended for local development with trusted datasets. Do not expose arbitrary code execution to untrusted users without implementing proper process isolation.

## Future Improvements

- Sandboxed visualisation execution.
- Support for additional database engines.
- Conversational follow-up queries.
- Query history and saved visualisations.
- Improved SQL evaluation and semantic correctness checks.
- Support for larger datasets.
- Additional visualisation types.

## License

See the repository's `LICENSE` file for licensing information.
