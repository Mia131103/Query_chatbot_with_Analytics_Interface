import plotly.express as px
import pandas as pd
from typing import TypedDict, Any
from pydantic import BaseModel

class ChartSpecs(BaseModel):
    type: str
    x: str
    y: str
    title: str

class Analytics_result(TypedDict):
    title: str
    figure: Any
    description: str

def build_chart(df: pd.DataFrame, spec: ChartSpecs):
    chart_type = spec.type.value.lower().strip()
    if chart_type == "bar":
        figure = px.bar(df, x=spec.x, y=spec.y, title=spec.title)
    elif chart_type == "line":
        figure = px.line(df, x=spec.x, y=spec.y, title=spec.title)
    elif chart_type == "scatter":
        figure = px.line(df, x=spec.x, y=spec.y, title = spec.title)
    elif chart_type == "histogram":
        figure = px.histogram(df, x=spec.x, y=spec.y, title=spec.title)
    elif chart_type == "pie":
        figure = px.pie(df, names=spec.x, values=spec.y, title=spec.title)
    elif chart_type == "box":
        figure = px.pie(df, x=spec.x, y=spec.y, title = spec.title)
    else: 
        raise ValueError(f"Unsupported chart type: {spec.type}")
    return figure