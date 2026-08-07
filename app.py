import streamlit as st
import pandas as pd
from SQL_generator import run_agent
from analytics_agent import run_analytics
from langchain_core.messages import HumanMessage, AIMessage

if "messages" not in st.session_state:
    st.session_state.messages = []
if "previous_sql" not in st.session_state:
    st.session_state.previous_sql = ""

st.set_page_config(
    page_title="SQL Analytics Agent",
    layout="wide"
)
st.title("SQL Analytics Agent")

sql_tab, analytics_tab = st.tabs(
    ["SQL Query", "Analytics"]
)

with sql_tab:
    st.write("SQL Query Page")

    question = st.text_area(
            "Ask your question"
        )
    generate = st.button("Generate SQL")

with analytics_tab:
    st.write("Analytics Page")
            
    st.header("Analytics")
    st.info("Run a SQL query first.")
    
if generate:
    with st.spinner("Generating SQL..."):
        st.session_state.messages.append(HumanMessage(content=question))
        result = run_agent(st.session_state.messages, st.session_state.previous_sql)
        st.session_state.previous_sql = result["sql"]
        df = pd.DataFrame(result["data"])

        with sql_tab:
            st.subheader("Generated SQL")
            st.code(
                result["sql"],
                language = "sql"
            )

            st.subheader("Results")
            st.dataframe(df, use_container_width=True)

            if result["execute_error"]:
                st.error(result["execute_error"])
            if result["llm_critique"]:
                st.error(result["llm_critique"])

        with analytics_tab:
            charts = run_analytics(result)

            for chart in charts:
                st.subheader(chart['title'])
                if chart["figure"] is not None:
                    st.plotly_chart(chart['figure'], width="stretch")
                st.write(chart['description'])




