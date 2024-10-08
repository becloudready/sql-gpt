import streamlit as st
import psycopg2
import pandas as pd
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# PostgreSQL credentials from .env file
DB_HOST = "localhost"         # Docker container is exposed on localhost
DB_PORT = "5432"              # PostgreSQL default port
DB_NAME = "mydatabase"        # Set in Docker command using POSTGRES_DB
DB_USER = "myuser"            # Set in Docker command using POSTGRES_USER
DB_PASSWORD = "mypassword"    # Set in Docker command using POSTGRES_PASSWORD
OLLAMA_SERVER_URL = "http://localhost:11434"  # Assuming your Ollama server is running on localhost with port 11400

# Function to get the schema of the PostgreSQL database
def get_db_schema():
    conn = None
    schema_info = ""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        # Get table and column details
        cur.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """)
        rows = cur.fetchall()
        schema_info += "Database Schema:\n\n"
        for table_name, column_name, data_type in rows:
            schema_info += f"Table: {table_name}, Column: {column_name}, Type: {data_type}\n"
        cur.close()
    except Exception as e:
        st.error(f"Error retrieving schema: {e}")
    finally:
        if conn is not None:
            conn.close()
    return schema_info

# Function to convert natural language to SQL using Ollama LLaMA 3.2
def nl_to_sql(natural_language_query, schema_info):
    prompt = f"Given the following database schema:\n\n{schema_info}\n\n Create sql query for this question {natural_language_query}\n\nonly return the sql query dont return and description of explaination"
    print("=======",prompt)
    payload = {
        "model": "llama3.2:1b",
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(f"{OLLAMA_SERVER_URL}/api/generate", json=payload)
        
        response.raise_for_status()
        result = response.json()
        # Extract the generated SQL query from the response
        sql_query = result["response"].strip()
        return sql_query
    except requests.exceptions.RequestException as e:
        return f"Error communicating with Ollama: {str(e)}"

# Function to execute SQL query on PostgreSQL
def run_query(query):
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute(query)
        if cur.description:
            # Fetch column names
            colnames = [desc[0] for desc in cur.description]
            # Fetch all rows
            rows = cur.fetchall()
            # Create a DataFrame for display
            result_df = pd.DataFrame(rows, columns=colnames)
            cur.close()
            return result_df
        else:
            conn.commit()
            return "Query executed successfully but no results to display."
    except Exception as e:
        return f"Error executing query: {e}"
    finally:
        if conn is not None:
            conn.close()

# Streamlit App Interface
st.title("DB Copilot: Natural Language to SQL")
st.markdown("### Enter a natural language query to interact with your PostgreSQL database")

# Display the schema of the database
with st.expander("Show Database Schema"):
    schema_info = get_db_schema()
    st.text(schema_info)

# Input field for natural language query
natural_language_query = st.text_area("Your query in plain English:")

# Generate SQL and execute on PostgreSQL
if st.button("Generate SQL and Run"):
    if natural_language_query:
        with st.spinner("Generating SQL using LLaMA 3.2..."):
            sql_query = nl_to_sql(natural_language_query, schema_info)
            st.subheader("Generated SQL Query")
            st.code(sql_query, language="sql")

        with st.spinner("Executing SQL on PostgreSQL..."):
            query_result = run_query(sql_query)
            if isinstance(query_result, str):
                st.error(f"Error: {query_result}")
            else:
                st.success("Query executed successfully!")
                if isinstance(query_result, pd.DataFrame) and not query_result.empty:
                    st.subheader("Query Results")
                    st.dataframe(query_result)

                    # Chart type dropdown
                    chart_type = st.selectbox("Select chart type to visualize results", ["None", "Line Chart", "Bar Chart", "Area Chart", "Pie Chart"])

                    # Display the selected chart
                    if chart_type == "Line Chart":
                        st.line_chart(query_result)
                    elif chart_type == "Bar Chart":
                        st.bar_chart(query_result)
                    elif chart_type == "Area Chart":
                        st.area_chart(query_result)
                    elif chart_type == "Pie Chart":
                        # For pie chart, we need to select only one categorical and one numerical column
                        if len(query_result.columns) >= 2:
                            x_column = st.selectbox("Select a categorical column for the Pie Chart:", query_result.columns)
                            y_column = st.selectbox("Select a numerical column for the Pie Chart:", query_result.columns)
                            if pd.api.types.is_numeric_dtype(query_result[y_column]):
                                pie_chart_data = query_result.groupby(x_column)[y_column].sum().reset_index()
                                st.write(pie_chart_data.set_index(x_column).plot.pie(y=y_column, autopct="%1.1f%%", legend=False))
                            else:
                                st.warning(f"Column '{y_column}' is not numeric. Select a different column for the pie chart.")
                        else:
                            st.warning("Pie chart requires at least one categorical and one numerical column.")
                else:
                    st.write("No results returned by the query.")
    else:
        st.warning("Please enter a natural language query.")