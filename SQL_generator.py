from langgraph.graph import StateGraph, END
from typing import Annotated, TypedDict, Any
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv, find_dotenv 
from pydantic import BaseModel
from database import schema, data_dictionary, query_db
from prompts import relevance_check_prompt, SQL_generation_prompt, llm_verification_prompt, resolved_request_prompt, SQL_generation_error_prompt

#Loading env and making our tool
load_dotenv(find_dotenv())

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

    relevance: bool
    response: str

class SQLCheck(BaseModel):
    valid: bool
    error: str

class RelevanceCheck(BaseModel):
    relevance: bool
    response: str

# === CREATING ALL NODE FUNCTIONS ===

#Relevance check node
def relevance_check_node(state: AgentState):
    messages = [
        SystemMessage(content=relevance_check_prompt.format(schema=schema, data_dictionary=data_dictionary))
    ] + state['messages']
    response = model.with_structured_output(RelevanceCheck).invoke(messages)
    return {"relevance": response.relevance, "response": response.response}

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
        query_db(state['sql'])
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

#Resolved request node
def resolved_node(state: AgentState):
    messages = [
        SystemMessage(content=resolved_request_prompt),
        HumanMessage(content= state['sql'])
    ]
    response = model.invoke(messages)
    return {"resolved_request": response.content}

#Fetching the actual data node
def fetch_data_node(state: AgentState):
    result = query_db(state['sql'])
    rows = [
        dict(zip(result.column_names, row))
        for row in result.result_rows
    ]
    return {"data": rows}

# === CONDITIONAL EDGE FUNCTIONS ===

#Is question relevant
def is_relevant(state: AgentState):
    return state["relevance"]

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

builder.add_node("Relevance_Check", relevance_check_node)
builder.add_node("SQL_Generation", SQL_generation_node)
builder.add_node("LLM_verification", llm_verification_node)
builder.add_node("Execute_verification", execute_verification_node)
builder.add_node("SQL_Regeneration", SQL_regeneration_node)
builder.add_node("Fetch_data", fetch_data_node)
builder.add_node("Resolved_request", resolved_node)

builder.set_entry_point("Relevance_Check")
builder.add_conditional_edges(
    "Relevance_Check",
    is_relevant,
    {
        True: "SQL_Generation",
        False: END
    }
)
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
        "resolved_request": "",
        "relevance": False,
        "response": ""
    }
    final_state = graph.invoke(state)
    return final_state