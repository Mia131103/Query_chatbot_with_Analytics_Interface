from langgraph.graph import StateGraph, END
from typing import Annotated, TypedDict, Any
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv, find_dotenv 
from pydantic import BaseModel
from database import get_schema, db, data_dictionary

#Loading env and making our tool
load_dotenv(find_dotenv())
#loading the schema
schema = get_schema(db)

class AgentState(TypedDict):
   # user: str
    messages: Annotated[list[AnyMessage], add_messages]

    sql: str
    prev_sql: str

    llm_critique: str
    execute_error: str
    data: list[dict[str, Any]]
    regenerations: int

    resolved_request: str

class SQLCheck(BaseModel):
    valid: bool
    error: str

# === PROMPT FOR EACH LLM NODE ===

#SQL generating node
SQL_generation_prompt = """You are an expert SQL generating assistant.\

You are given the user question, the user messages history and the SQL generated for the last question.\

You are querying a ClickHouse database.\

Use the database schema provided in {schema} and the data dictionary provided in {data_dictionary}
for more information on the schema, column meanings, relationships and data types.\

Generate SQL for the user question.\
If the latest request is a follow up question, modify the previous SQL accordingly.
Otherwise, generate a new SQL query.\

IMPORTANT CLICKHOUSE RULES:

1. Use ClickHouse SQL syntax only.

2. Do NOT use SQL functions from other database systems when an equivalent
   ClickHouse function exists.

3. For categorical columns, use LIKE when matching natural-language
   categorical values where minor formatting differences may exist.

   Example:
   appointment_type LIKE '%follow-up%'

4. All values in the database are in Title Case.

5. Do not use CURDATE(). Use today() for the current date.

6. Only use columns that exist in the schema.

7. Only generate SELECT statements.

8. Give appropriate column names to any output columns that are
   aggregated or calculated.

Return ONLY executable SQL.
Do not wrap it in markdown.
Do not explain your answer.
Do not include ```sql.
"""

#LLM verification node
llm_verification_prompt = """
You are an SQL debugger. \

Check the given SQL generated for the given user question for logical and syntax errors. \
Make sure it is a SELECT statement, not INSERT, DELETE, UPDATE etc \
Use the {schema} and the {data_dictionary} to check for these errors. \

Do not pick errors over efficiency or be nitpicky. \
Only give error when it will definitely cause the query to fail or given incorrect results.\

Response should be generated according to the provided structured output.\
"""

#SQL generation on error
SQL_generation_error_prompt = """You are an expert SQL generator. \
You are given the latest user question, the SQL generated against that question, and the error in that code. \
Use the {schema} and the {data_dictionary} to understand the database.\

Your task is to fix the problem in the SQL according to the error given and generate the new SQL code. \
Do not change the intent of the query unless the error clearly requires it. \

ONLY generate SELECT statements. \
Give appropriate column names to any output columns that are aggregated or calculated. \

Return ONLY corrected executable SQL.
Do not wrap it in markdown.
Do not explain your answer.
Do not include ```sql. """

#Resolved request prompt
resolved_request_prompt = """
You will be given the chat history of a user and AI assistanat. \
Your task is to deduce the full request of the user in one concise sentence. \

That means if there are follow up questions, find the first question and then all the follow ups and summarise all the requests into one.
If it is a new question, then just output the questions as it is.

Respond ONLY in one line with that request."""

# === CREATING ALL NODE FUNCTIONS ===

#SQL Gneration node
def SQL_generation_node(state: AgentState):
    latest_user = state['messages'][-1].content
    UserMessage = HumanMessage(
        content=f"User Question: {latest_user}\nPrevious SQL: {state['prev_sql']}\nChat history:"
    )
    messages = [
        SystemMessage(content=SQL_generation_prompt.format(schema=schema, data_dictionary=data_dictionary)),
        UserMessage
    ] + state['messages'][:-1]
    response = model.invoke(messages)
    return {"sql": response.content}

#LLM verification node
def llm_verification_node(state: AgentState):
    latest_user = state['messages'][-1].content
    UserMessage = HumanMessage(
        content=f"User Question: {latest_user}\nSQL generated: {state['sql']}"
    )
    messages = [
        SystemMessage(content=llm_verification_prompt.format(schema=schema, data_dictionary=data_dictionary)),
        UserMessage
    ]
    response = model.with_structured_output(SQLCheck).invoke(messages)
    return {"llm_critique": response.error}

#Execute testing
def execute_verification_node(state: AgentState):
    sql = state['sql'].strip().upper()
    if not sql.startswith("SELECT"):
        return {"execute_error": "Only SELECT statements are allowed."}

    try:
        db.query(state['sql'])
        return {"execute_error": ""}
    except Exception as e:
        return {"execute_error": str(e)}

#SQL Regeneration node
def SQL_regeneration_node(state: AgentState):
    error = (state["llm_critique"] or state['execute_error'])
    latest_user = state['messages'][-1].content
    UserMessage = HumanMessage(
        content=f"User Question: {latest_user}\n\nGenerated SQL: {state['sql']}\n\nError: {error}"
    )
    messages = [
        SystemMessage(content=SQL_generation_error_prompt.format(schema=schema, data_dictionary=data_dictionary)),
        UserMessage
    ]
    response = model.invoke(messages)
    return {
        "sql": response.content, 
        "llm_critique": "",
        "execute_error": "",
        "regenerations": state.get("regenerations", 1) + 1
    }

#Fetching the actual data node
def fetch_data_node(state: AgentState):
    result = db.query(state["sql"])
    rows = [
        dict(zip(result.column_names, row))
        for row in result.result_rows
    ]
    return {"data": rows}

#Resolved request node
def resolved_node(state: AgentState):
    messages = [
        SystemMessage(content=resolved_request_prompt)
    ] + state['messages']
    response = model.invoke(messages)
    return {"resolved_request": response.content}

# === CONDITIONAL EDGE FUNCTIONS ===

#Has LLM verified
def llm_verified(state: AgentState):
    if state['regenerations'] < 3:
            return state['llm_critique'] == ""
    return True

#Has execute verified
def execute_verified(state: AgentState):
    if state['regenerations'] < 3:
        return state['execute_error'] == ""
    return True

# === BUILDING THE GRAPH ===

builder = StateGraph(AgentState)

builder.add_node("SQL_Generation", SQL_generation_node)
builder.add_node("LLM_verification", llm_verification_node)
builder.add_node("Execute_verification", execute_verification_node)
builder.add_node("SQL_Regeneration", SQL_regeneration_node)
builder.add_node("Fetch_data", fetch_data_node)
builder.add_node("Resolved_request", resolved_node)

builder.set_entry_point("SQL_Generation")
builder.add_edge("SQL_Generation", "LLM_verification")
builder.add_conditional_edges(
    "LLM_verification",
    llm_verified,
    {True: "Execute_verification", False: "SQL_Regeneration"}
)
builder.add_conditional_edges(
    "Execute_verification",
    execute_verified,
    {True: "Resolved_request", False: "SQL_Regeneration"}
)
builder.add_edge("SQL_Regeneration", "LLM_verification")
builder.add_edge("Resolved_request", "Fetch_data")
builder.add_edge("Fetch_data", END)

model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
graph = builder.compile()

def run_agent(messages: list[AnyMessage], previous_sql: str) -> dict:
    state = {
        "messages": messages,
        "sql": "",
        "prev_sql": previous_sql,
        "llm_critique": "",
        "execute_error": "",
        "data": [],
        "regenerations": 0,
        "resolved_request": ""
    }
    final_state = graph.invoke(state)
    return final_state