import streamlit as st
import pandas as pd
from SQL_generator import run_agent

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
    
    if generate:
        with st.spinner("Generating SQL..."):
            result = run_agent(question)

            st.subheader("Generated SQL")
            st.code(
                result["sql"],
                language = "sql"
            )

            df = pd.DataFrame(result["data"])
            st.subheader("Results")
            st.dataframe(df, use_container_width=True)

            if result["execute_error"]:
                st.error(result["execute_error"])
            if result["llm_critique"]:
                st.error(result["llm_critique"])
    

with analytics_tab:
    st.write("Analytics Page")
    
    st.header("Analytics")
    st.info("Run a SQL query first.")



