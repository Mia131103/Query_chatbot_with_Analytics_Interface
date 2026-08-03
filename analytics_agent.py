from langgraph.graph import StateGraph, END
from typing import TypedDict, Any
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv, find_dotenv 
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
import pandas as pd
from visualisations import build_chart
from enum import Enum

load_dotenv(find_dotenv())

class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    PIE = "pie"
    HISTOGRAM = "histogram"
    BOX = "box"

class AgentState(TypedDict):
    question: str
    sql: str
    chart_specs: list[dict]
    descriptions: list[str]

class ChartSpecs(BaseModel):
    type: ChartType
    x: str
    y: str
    title: str

class ChartList(BaseModel):
    charts: list[ChartSpecs]

class Analytics_result(TypedDict):
    title: str
    figure: Any
    description: str


# === PROMPTS FOR THE LLM NODES ===

#Planner
planner_prompt = """You are an analytics expert. \
You take the user question and the sql code generated against the user request. \
Generate between 1 and 4 most useful visualisations given the context. \
Never invent columns.\
Do not write python.\
Respond ONLY in the output structure provided.\
'type' MUST be EXACTLY one of:

bar\
line\
scatter\
pie\
histogram\
box\
"""

#Generating insights
generate_insight_prompt = """You are a bussiness analyst.
You are given the user question, sql, and the chart specifications.\
Generate a concise sentence explaining the main takeaway from the chart. \
Do not invent facts.\
Only use the data given.
"""

# === FUNCTIONS FOR GRAPH NODES ===

#Planner node
def planner_node(state: AgentState):
    UserMessage = HumanMessage(content=f"User Question: {state['question']}\n\nSQL geenrated: {state['sql']}")
    messages = (
        SystemMessage(content=planner_prompt),
        UserMessage
    )
    response = model.with_structured_output(ChartList).invoke(messages)
    return {"chart_specs": response.charts}
    
#Generate Insights node
def generate_insight_node(state: AgentState):
    descriptions = []
    for spec in state['chart_specs']:
        messages = (
            SystemMessage(content=generate_insight_prompt),
            HumanMessage(content=f"""
                         User question: {state['question']}\n
                         SQL: {state['sql']}\n
                         Chart specifications:
                         Chart title {spec.title}\n
                         Chart type {spec.type}\n
                         X axis: {spec.x}\n
                         Y axis: {spec.y}""")
        )
        response = model.invoke(messages)
        descriptions.append(response.content)
    return {"descriptions": descriptions}

# === BUILDING THE GRAPH ===
builder = StateGraph(AgentState)
builder.add_node("Planner", planner_node)
builder.add_node("Generate_Insights", generate_insight_node)
builder.set_entry_point("Planner")
builder.add_edge("Planner", "Generate_Insights")
builder.add_edge("Generate_Insights", END)

model = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def run_analytics(result: dict) -> list[dict]:

    with SqliteSaver.from_conn_string(":memory:") as memory:

        graph = builder.compile(checkpointer=memory)
        thread = {"configurable": {"thread_id": "1"}}
        state = {
            "question": result['user'],
            "sql": result['sql'],
            "chart_specs": [],
            "descriptions": []
        }
        final_state = graph.invoke(state, thread)

        df = pd.DataFrame(result['data'])
        analytics: list[Analytics_result] = []
        for spec, desc in zip(final_state['chart_specs'], final_state['descriptions']):
            fig = build_chart(df, spec)
            analytics.append({
                "title": spec.title,
                "figure": fig,
                "description": desc
            })
        return analytics
