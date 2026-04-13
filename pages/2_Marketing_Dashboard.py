import pandas as pd
import plotly.express as px
import streamlit as st

from utils import (
    prepare_data,
    format_number,
    format_currency,
    format_percent,
    top_group,
    monthly_summary,
    convert_df_to_csv,
)

st.set_page_config(page_title="Marketing Dashboard", layout="wide")
st.title("Marketing Dashboard")

df = prepare_data()
if df.empty:
    st.warning("Data tidak tersedia.")
    st.stop()

filtered = df.copy()

# Sidebar marketing
st.sidebar.header("Marketing Filter")

if "source_sheet" in filtered.columns:
    years = sorted(filtered["source_sheet"].dropna().unique().tolist())
    selected_years = st.sidebar.multiselect("Tahun", years, default=years)
    filtered = filtered[filtered["source_sheet"].isin(selected_years)]

if "Platform" in filtered.columns:
    platforms = sorted(filtered["Platform"].dropna().unique().tolist())
    selected_platforms = st.sidebar.multiselect("Platform", platforms, default=platforms)
    filtered = filtered[filtered["Platform"].isin(selected_platforms)]

if "Recipient Country" in filtered.columns:
    countries = sorted(filtered["Recipient Country"].dropna().unique().tolist())
    selected_countries = st.sidebar.multiselect("Recipient Country", countries, default=countries)
    filtered = filtered[filtered["Recipient Country"].isin(selected_countries)]

if "Account Type" in filtered.columns:
    account_types = sorted(filtered["Account Type"].dropna().unique().tolist())
    selected_accounts = st.sidebar.multiselect("Account Type", account_types, default=account_types)
    filtered = filtered[filtered["Account Type"].isin(selected_accounts)]

if "Purpose" in filtered.columns:
    purposes = sorted(filtered["Purpose"].dropna().unique().tolist())
    selected_purposes = st.sidebar.multiselect("Purpose", purposes, default=purposes)
    filtered = filtered[filtered["Purpose"].isin(selected_purposes)]
if "Transaction Date" in filtered.columns and filtered["Transaction Date"].notna().any():
    min_dt = filtered["Transaction Date"].min().date()
    max_dt = filtered["Transaction Date"].max().date()

    if "marketing_date_range" not in st.session_state:
        st.session_state["marketing_date_range"] = [min_dt, max_dt]

    current_range = st.session_state["marketing_date_range"]

    if isinstance(current_range, (list, tuple)) and len(current_range) == 2:
        current_start, current_end = current_range
    else:
        current_start, current_end = min_dt, max_dt

    # Sesuaikan value agar tidak keluar dari batas data terbaru
    if current_start < min_dt or current_start > max_dt:
        current_start = min_dt
    if current_end > max_dt or current_end < min_dt:
        current_end = max_dt
    if current_start > current_end:
        current_start = min_dt
        current_end = max_dt

    date_range = st.sidebar.date_input(
        "Custom Date",
        value=[current_start, current_end],
        min_value=min_dt,
        max_value=max_dt,
        key="marketing_date_range",
    )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered = filtered[
            (filtered["Transaction Date"] >= pd.to_datetime(start_date)) &
            (filtered["Transaction Date"] < pd.to_datetime(end_date) + pd.Timedelta(days=1))
        ]    

# KPI marketing
total_tx = len(filtered)
total_amount = filtered["Amount Sent"].sum() if "Amount Sent" in filtered.columns else 0
avg_amount = filtered["Amount Sent"].mean() if "Amount Sent" in filtered.columns else 0
unique_sender = filtered["Name"].nunique() if "Name" in filtered.columns else 0
repeat_sender = 0
if "Name" in filtered.columns:
    repeat_sender = int((filtered["Name"].value_counts() > 1).sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Transactions", format_number(total_tx))
c2.metric("Total Amount", format_currency(total_amount))
c3.metric("Avg Amount", format_currency(avg_amount))
c4.metric("Unique Sender", format_number(unique_sender))
c5.metric("Repeat Sender", format_number(repeat_sender))

# Channel performance
st.subheader("Channel Performance")

col1, col2 = st.columns(2)

with col1:
    platform_summary = top_group(filtered, "Platform").head(10)
    if not platform_summary.empty:
        fig = px.bar(platform_summary, x="Platform", y="transactions", title="Transactions by Platform")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    platform_summary = top_group(filtered, "Platform").head(10)
    if not platform_summary.empty and "total_amount" in platform_summary.columns:
        fig = px.bar(platform_summary, x="Platform", y="total_amount", title="Amount by Platform")
        st.plotly_chart(fig, use_container_width=True)

# Market opportunity
st.subheader("Market Opportunity")

col3, col4 = st.columns(2)

with col3:
    country_summary = top_group(filtered, "Recipient Country").head(10)
    if not country_summary.empty:
        fig = px.bar(country_summary, x="Recipient Country", y="transactions", title="Top Recipient Country")
        st.plotly_chart(fig, use_container_width=True)

with col4:
    purpose_summary = top_group(filtered, "Purpose").head(10)
    if not purpose_summary.empty:
        fig = px.bar(purpose_summary, x="Purpose", y="transactions", title="Purpose Distribution")
        st.plotly_chart(fig, use_container_width=True)

# Customer behavior
with st.expander("Customer Behavior"):
    col5, col6, col7 = st.columns(3)
with col5:
    account_summary = top_group(filtered, "Account Type")
    if not account_summary.empty:
        fig = px.pie(account_summary, names="Account Type", values="transactions", title="Account Type Mix")
        st.plotly_chart(fig, use_container_width=True)

with col6:
    payment_summary = top_group(filtered, "Payment Method").head(10)
    if not payment_summary.empty:
        fig = px.bar(payment_summary, x="Payment Method", y="transactions", title="Payment Method Performance")
        st.plotly_chart(fig, use_container_width=True)

with col7:
    sender_summary = top_group(filtered, "Name").head(10)
    if not sender_summary.empty:
        fig = px.bar(sender_summary, x="Name", y="transactions", title="Top Active Sender")
        st.plotly_chart(fig, use_container_width=True)

# Monthly trends
st.subheader("Monthly Marketing Trend")
ms = monthly_summary(filtered)
if not ms.empty:
    col8, col9 = st.columns(2)

    with col8:
        fig = px.line(ms, x="period", y="transactions", markers=True, title="Monthly Transactions")
        st.plotly_chart(fig, use_container_width=True)

    with col9:
        fig = px.line(ms, x="period", y="total_amount", markers=True, title="Monthly Amount")
        st.plotly_chart(fig, use_container_width=True)

# Simple marketing insights
st.subheader("Marketing Insights")

insights = []

if "Platform" in filtered.columns and not filtered.empty:
    top_platform = top_group(filtered, "Platform")
    if not top_platform.empty:
        row = top_platform.iloc[0]
        insights.append(f"Platform paling efektif saat ini adalah {row['Platform']} dengan {format_number(row['transactions'])} transaksi.")

if "Recipient Country" in filtered.columns and not filtered.empty:
    top_country = top_group(filtered, "Recipient Country")
    if not top_country.empty:
        row = top_country.iloc[0]
        insights.append(f"Market tujuan terkuat ada di {row['Recipient Country']} dengan {format_number(row['transactions'])} transaksi.")

if "Purpose" in filtered.columns and not filtered.empty:
    top_purpose = top_group(filtered, "Purpose")
    if not top_purpose.empty:
        row = top_purpose.iloc[0]
        insights.append(f"Purpose paling dominan adalah {row['Purpose']}.")

insights.append(f"Jumlah repeat sender saat ini adalah {format_number(repeat_sender)}.")
insights.append(f"Rata-rata nominal transaksi berada di {format_currency(avg_amount)}.")

for i, insight in enumerate(insights, start=1):
    st.write(f"{i}. {insight}")

# Detailed tables
with st.expander("Detail Marketing Tables"):
    st.write("Top Platform")
    st.dataframe(top_group(filtered, "Platform").head(20), use_container_width=True)

    st.write("Top Countries")
    st.dataframe(top_group(filtered, "Recipient Country").head(20), use_container_width=True)

    st.write("Top Senders")
    st.dataframe(top_group(filtered, "Name").head(20), use_container_width=True)

    st.write("Filtered Data")
    display_filtered = filtered.copy()
    if "Amount Sent" in display_filtered.columns:
        display_filtered["Amount Sent"] = display_filtered["Amount Sent"].apply(format_currency)
    if "Recipient Gets amount" in display_filtered.columns:
        display_filtered["Recipient Gets amount"] = display_filtered["Recipient Gets amount"].apply(format_number)
    if "Admin Fee (IDR)" in display_filtered.columns:
        display_filtered["Admin Fee (IDR)"] = display_filtered["Admin Fee (IDR)"].apply(format_currency)

    st.dataframe(display_filtered.head(200))

csv_data = convert_df_to_csv(filtered)
st.download_button(
    label="Download marketing data as CSV",
    data=csv_data,
    file_name="marketing_filtered_data.csv",
    mime="text/csv",
    key="download_marketing_csv",
    on_click="ignore",
)