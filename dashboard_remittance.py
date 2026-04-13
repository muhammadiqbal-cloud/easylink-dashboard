import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("Test Google Sheets")

st.write("connections loaded:", "connections" in st.secrets)

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    st.write("Connection object created")

    df = conn.read(ttl=0)
    st.success("Berhasil baca spreadsheet default")
    st.write(df.head())
except Exception as e:
    st.error(f"Error default read: {e}")