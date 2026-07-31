import streamlit as st
import pandas as pd
from SQL_generator import run_agent
from visualisations import default_analytics
from analytics_agent import run_analytics

st.set_page_config(
    page_title="SQL Analytics Agent",
    layout="wide"
)
st.title("SQL Analytics Agent")

sql_tab, analytics_tab = st.tabs(
    ["SQL Querry", "Analytics"]
)

with sql_tab:
    st.write("SQL Query Page")

    question = st.text_area(
            "Ask your question",
            placeholder="Example: Show average salary by department"
        )
    generate = st.button("Generate SQL")

with analytics_tab:
    st.write("Analytics Page")
            
    st.header("Analytics")
    st.info("Run a SQL query first.")
    
if generate:
    with st.spinner("Generating SQL..."):
        result = run_agent(question)
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

            #    if question == "":
            #       charts = default_analytics()
            #   else:
            #       charts = run_analytics(result)
            charts = run_analytics(result)

            for chart in charts:
                st.subheader(chart['title'])
                st.plotly_chart(chart['figure'], use_container_width=True)
                st.write(chart['description'])




