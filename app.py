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
    st.write("Hello! How can I help you today?")
    question = st.text_area("Ask Database related question.")
    generate = st.button("Generate SQL")
    
if generate:
    st.session_state.messages.append(HumanMessage(content=question))
    result = run_agent(st.session_state.messages, st.session_state.previous_sql)

    if not result["relevance"]:
        st.session_state.messages.append(AIMessage(content=result["response"]))
        st.warning(result["response"])
    else: 
        st.session_state.previous_sql = result["sql"]
        df = pd.DataFrame(result["data"])

        with sql_tab:
            with st.spinner("Generating SQL..."):

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
            with st.spinner("Generating Analytics..."):

                charts = run_analytics(result)

                if not charts: 
                    st.info("No meaningful analytics could be generated.")
                else:
                    for i in range(0, len(charts), 2):
                        col1, col2 = st.columns(2)

                        with col1:
                            chart = charts[i]
                            st.subheader(chart['title'])
                            st.plotly_chart(chart['figure'], width="stretch", config={"displayModBar": False})
                            st.caption(chart['description'])

                        if i+1 < len(charts):
                            with col2:
                                chart = charts[i + 1]
                                st.subheader(chart['title'])
                                st.plotly_chart(chart['figure'], width="stretch", config={"displayModBar": False})
                                st.caption(chart['description'])




