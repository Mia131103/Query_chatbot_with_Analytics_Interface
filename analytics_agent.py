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
from database import get_schema, data_dictionary, db
from SQL_generator import run_agent

load_dotenv(find_dotenv())
schema = get_schema(db)

#For analytics agent state
class AgentState(TypedDict):
    question: str
    sql: str
    chart_specs: list[dict]

    #Chart specifications for each chart to be generated
class ChartSpecs(BaseModel):
    title: str
    goal: str
    type: ChartType
    sql: str
    x: str = ""
    y: str = ""
    description: str = ""

class ChartList(BaseModel):
    charts: list[ChartSpecs]

#For 'type' in chart spec
class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    PIE = "pie"
    HISTOGRAM = "histogram"
    BOX = "box"

#Return type for chart axis node
class chartAxis(BaseModel):
    x: str
    y: str

#Return type for the run_analytics function
class Analytics_result(TypedDict):
    title: str
    figure: Any
    description: str


# === PROMPTS FOR THE LLM NODES ===

#planner 
planner_prompt = """You are an analytics expert. \
You are given the user question and the sql code generated against the user request. \
You work for a healthcare provider. \
Deduce 1 to 4 visualisations that would be useful for a healthcare provider to see. \
It is not necessary that the visualisations are directly related to the user question. \
Use the {schema} and the {data_dictionary} to better understand the database and the relations between tables. \

Provide the title, goal of the visualisation and the type of chart to be generated. \
Goal of the visualisation should be a concise sentence describing the purpose of the visualisation. \
'type' MUST be EXACTLY one of:
bar\
line\
scatter\
pie\
histogram\
box\

Respond ONLY in the output structure's title, goal and type fields.
"""

#Chart specifications
chart_specs_prompt = """You are a graph agent.
You are given the title of the chart, goal of the visualisation and the type of chart to be generated. \
Column names and their data types are also given; Use ONLY this to create x and y labels. \
Never invent columns.\
Never rename columns.\
Never convert snake_case to Title Case.\

Respond ONLY in the output structure's x and y fields.
"""

#Generating insights
generate_insight_prompt = """You are a bussiness analyst.
You are given the user question, and the chart specifications: goal, title, type, x and y labels.\
Generate a concise phrase explaining the main takeaway from the chart. \
Do not invent facts.\
Only use the data given."""

# === FUNCTIONS FOR GRAPH NODES ===

#Planner node
def planner_node(state: AgentState):
    UserMessage = HumanMessage(content=f"User Question: {state['question']}\n\nSQL geenrated: {state['sql']}")
    messages = (
        SystemMessage(content=planner_prompt.format(schema=schema, data_dictionary=data_dictionary)),
        UserMessage
    )
    response = model.with_structured_output(ChartList).invoke(messages)
    return {"chart_specs": response.charts}

#SQL_agent node
def SQL_agent_node(state: AgentState):
    for chart in state['chart_specs']:
        messages = [HumanMessage(content=chart.goal)]
        result = run_agent(messages, previous_sql="")
        chart.sql = result['sql']
    return {"chart_specs": state['chart_specs']}

#Chart specification node
def chart_spec_node(state: AgentState):
    for chart in (state['chart_specs']):
        data = db.query(chart.sql)
        df = pd.DataFrame(data.result_rows, columns=data.column_names)
        dtypes = df.dtypes.apply(lambda x: x.name).to_dict()
        userMessage = HumanMessage(content=f"Title: {chart.title}\n Goal: {chart.goal}\n Graph Type: {chart.type}\n Data Types: {dtypes}")
        messages = (
            SystemMessage(content=chart_specs_prompt),
            userMessage
        )
        response = model.with_structured_output(chartAxis).invoke(messages)
        chart.x = response.x
        chart.y = response.y
    return {"chart_specs": state['chart_specs']}

#Generate Insights node
def generate_insight_node(state: AgentState):
    for spec in state['chart_specs']:
        messages = (
            SystemMessage(content=generate_insight_prompt),
            HumanMessage(content=f"""
                         User question: {state['question']}\n
                         Chart goal: {spec.goal}\n
                         Chart title: {spec.title}\n
                         Chart type: {spec.type}\n
                         X axis: {spec.x}\n
                         Y axis: {spec.y}""")
        )
        response = model.invoke(messages)
        spec.description = response.content
    return {"chart_specs": state['chart_specs']}

# === BUILDING THE GRAPH ===
builder = StateGraph(AgentState)
builder.add_node("Planner", planner_node)
builder.add_node("SQL_agent", SQL_agent_node)
builder.add_node("Chart_specifications", chart_spec_node)
builder.add_node("Generate_Insights", generate_insight_node)
builder.set_entry_point("Planner")
builder.add_edge("Planner", "SQL_agent")
builder.add_edge("SQL_agent", "Chart_specifications")
builder.add_edge("Chart_specifications", "Generate_Insights")
builder.add_edge("Generate_Insights", END)

model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
graph = builder.compile()

def run_analytics(result: dict) -> list[dict]:

    if result['data'] == []:
        return [{
            "title": "No Results.",
            "figure": None,
            "description": "The query generated no rows. Analytics cannot be generated."
            }]

    state = {
        "question": result['resolved_request'],
        "sql": result['sql'],
        "chart_specs": []
    }
    final_state = graph.invoke(state)
    
    analytics: list[Analytics_result] = []
    for chart in (final_state['chart_specs']):
        data = db.query(chart.sql)
        df = pd.DataFrame(data.result_rows, columns=data.column_names)
        fig = build_chart(df, chart)
        analytics.append({
            "title": chart.title,
            "figure": fig,
            "description": chart.description
        })
    return analytics
