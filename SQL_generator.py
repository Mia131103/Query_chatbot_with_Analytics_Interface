from langgraph.graph import StateGraph, END
from typing import TypedDict, Any
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv, find_dotenv 
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
from database import get_schema, db, data_dictionary

#Loading env and making our tool
load_dotenv(find_dotenv())
#loading the schema
schema = get_schema(db)

class AgentState(TypedDict):
    user: str
    sql: str
    llm_critique: str
    execute_error: str
    data: list[dict[str, Any]]
    regenerations: int

class SQLCheck(BaseModel):
    valid: bool
    error: str

# === PROMPT FOR EACH LLM NODE ===

#SQL generating node
SQL_generation_prompt = """You are an expert SQL generating assistant.\
You are given the database schema provided in {schema}, the data dictionary provided in {data_dictionary} for more information on the schema and relations, and the user question. \
Generate SQL for the user question. \
ONLY generate SELECT statements. \

Return ONLY executable SQL.
Do not wrap it in markdown.
Do not explain your answer.
Do not include ```sql. """

#LLM verification node
llm_verification_prompt = """
You are an SQL debugger. \

Check the given SQL generated for the given user question for logical and syntax errors. \
Make sure it is a SELECT statement, not INSERT, DELETE, UPDATE etc \
Use the {schema} and the {data_dictionary} to check for these errors. \

Do not pick errors over efficiency or be nitpicky. \
Only give error when it will definitely cause the query to fail or \
given incorrect results.\

Response should be generated according to the provided structured output.\
"""

#SQL generation on error
SQL_generation_error_prompt = """You are an expert SQL generator. \
You are given the user question, the SQL generated against that question, and the error in that code. \
Fix the problem in the SQL according to the error given and generate the new SQL code. \
Use the {schema} and the {data_dictionary} to understand the database.\
ONLY generate SELECT statements. \

Return ONLY corrected executable SQL.
Do not wrap it in markdown.
Do not explain your answer.
Do not include ```sql. """

# === CREATING ALL NODE FUNCTIONS ===

#SQL Gneration node
def SQL_generation_node(state: AgentState):
    messages = [
        SystemMessage(content=SQL_generation_prompt.format(schema=schema, data_dictionary=data_dictionary)),
        HumanMessage(content=state['user'])
    ]
    response = model.invoke(messages)
    return {"sql": response.content}

#LLM verification node
def llm_verification_node(state: AgentState):
    UserMessage = HumanMessage(
        content=f"User Question: {state['user']}\nSQL generated: {state['sql']}"
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
    UserMessage = HumanMessage(
        content=f"User Question: {state['user']}\n\nGenerated SQL: {state['sql']}\n\nError: {error}"
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
    {True: "Fetch_data", False: "SQL_Regeneration"}
)
builder.add_edge("SQL_Regeneration", "LLM_verification")
builder.add_edge("Fetch_data", END)

model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def run_agent(question: str) -> dict:
    with SqliteSaver.from_conn_string(":memory:") as memory:
        
        graph = builder.compile(checkpointer=memory)
    
        thread = {"configurable": {"thread_id": "1"}}
        state = {
            "user": question,
            "sql": "",
            "llm_critique": "",
            "execute_error": "",
            "data": [],
            "regenerations": 0
        }
        final_state = graph.invoke(state, thread)
        return final_state