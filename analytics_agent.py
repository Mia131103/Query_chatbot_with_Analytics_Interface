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
from database import schema, data_dictionary, query_db
from prompts import planner_prompt, analytics_sql_prompt, chart_specs_prompt, generate_insight_prompt

load_dotenv(find_dotenv())

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

    for chart in state["chart_specs"]:
        prompt = f"""
        Chart title: {chart.title}
        Chart goal: {chart.goal}
        Chart type: {chart.type}
        Database schema:
        {schema}
        Data dictionary:
        {data_dictionary}
        """
        messages = [
            SystemMessage(content=analytics_sql_prompt),
            HumanMessage(content=prompt)
        ]
        response = model.invoke(messages)
        chart.sql = response.content
    return {"chart_specs": state["chart_specs"]}

#Chart specification node
def chart_spec_node(state: AgentState):
    for chart in (state['chart_specs']):
        data = query_db(chart.sql)
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

        data = query_db(chart.sql)

        #check if query had some bug
        if not data.column_names:
            continue
        df = pd.DataFrame(data.result_rows, columns=data.column_names)

        #check if query returned no rows
        if df.empty or chart.x not in df.columns or chart.y not in df.columns:
            continue

        fig = build_chart(df, chart)
        analytics.append({
            "title": chart.title,
            "figure": fig,
            "description": chart.description
        })
    return analytics
