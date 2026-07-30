import clickhouse_connect
from dotenv import load_dotenv, find_dotenv 
import os

load_dotenv(find_dotenv())

#Loading our database
db = clickhouse_connect.get_client(
    host=os.getenv("HOST"),
    port=int(os.getenv("PORT")),
    username=os.getenv("USER"),
    password=os.getenv("PASSWORD"),
    database=os.getenv("DATABASE"),
    secure= True
)

def get_schema(client):
    tables = client.query("""
    SELECT
        table,
        name,
        type
    FROM system.columns
    WHERE database = currentDatabase()
    ORDER BY table, position
    """).result_rows
    schema = {}
    for table, column, datatype in tables:
        schema.setdefault(table, []).append(f"{column} {datatype}")
    schema_text = ""
    for table, cols in schema.items():
        schema_text += f"Table: {table}\n"
        schema_text += "\n".join(cols)
        schema_text += "\n\n"
    return schema_text