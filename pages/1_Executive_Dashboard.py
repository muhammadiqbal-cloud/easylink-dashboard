import pandas as pd
import plotly.express as px
import streamlit as st

from utils import (
    prepare_data,
    format_number,
    format_currency,
    format_percent,
    monthly_summary,
    top_group,
    build_auto_insights,
    summarize_period,
    get_period_df,
    safe_pct_change,
)

st.set_page_config(page_title="Executive Dashboard", layout="wide")
st.title("Executive Dashboard")

df = prepare_data()
if df.empty:
    st.warning("Data tidak tersedia.")
    st.stop()

# Filter ringkas
st.sidebar.header("Executive Filter")

filtered = df.copy()

if "source_sheet" in filtered.columns:
    years = sorted(filtered["source_sheet"].dropna().unique().tolist())
    selected_years = st.sidebar.multiselect("Tahun", years, default=years)
    filtered = filtered[filtered["source_sheet"].isin(selected_years)]

if "Platform" in filtered.columns:
    platforms = sorted(filtered["Platform"].dropna().unique().tolist())
    selected_platforms = st.sidebar.multiselect("Platform", platforms, default=platforms)
    filtered = filtered[filtered["Platform"].isin(selected_platforms)]

if "Transaction Date" in filtered.columns and filtered["Transaction Date"].notna().any():
    min_dt = filtered["Transaction Date"].min().date()
    max_dt = filtered["Transaction Date"].max().date()
    date_range = st.sidebar.date_input(
        "Range Tanggal",
        value=[min_dt, max_dt],
        min_value=min_dt,
        max_value=max_dt,
    )
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        filtered = filtered[
            (filtered["Transaction Date"] >= pd.to_datetime(start_date)) &
            (filtered["Transaction Date"] < pd.to_datetime(end_date) + pd.Timedelta(days=1))
        ]

# KPI
total_tx = len(filtered)
total_amount = filtered["Amount Sent"].sum() if "Amount Sent" in filtered.columns else 0
avg_amount = filtered["Amount Sent"].mean() if "Amount Sent" in filtered.columns else 0
cancel_count = filtered["flag_canceled"].sum() if "flag_canceled" in filtered.columns else 0
cancel_rate = (cancel_count / total_tx * 100) if total_tx > 0 else 0
risk_count = (filtered["risk_score"] > 0).sum() if "risk_score" in filtered.columns else 0
success_rate = 100 - cancel_rate if total_tx > 0 else 0

ms = monthly_summary(filtered)
growth_pct = None
if len(ms) >= 2:
    growth_pct = safe_pct_change(ms.iloc[-1]["transactions"], ms.iloc[-2]["transactions"])

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Transactions", format_number(total_tx), delta=f"{growth_pct:.2f}%" if growth_pct is not None else None)
c2.metric("Total Amount Sent", format_currency(total_amount))
c3.metric("Avg Amount", format_currency(avg_amount))
c4.metric("Success Rate", format_percent(success_rate))
c5.metric("Cancel Rate", format_percent(cancel_rate))
c6.metric("Risk Transactions", format_number(risk_count))

# Trend utama
st.subheader("Monthly Trends")

col1, col2 = st.columns(2)

with col1:
    if not ms.empty:
        fig = px.line(ms, x="period", y="transactions", markers=True, title="Monthly Transaction Trend")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    if not ms.empty:
        fig = px.line(ms, x="period", y="total_amount", markers=True, title="Monthly Amount Trend")
        st.plotly_chart(fig, use_container_width=True)

# Top drivers
st.subheader("Top Business Drivers")

col3, col4, col5 = st.columns(3)

with col3:
    country_summary = top_group(filtered, "Recipient Country").head(10)
    if not country_summary.empty:
        fig = px.bar(country_summary, x="Recipient Country", y="transactions", title="Top Recipient Country")
        st.plotly_chart(fig, use_container_width=True)

with col4:
    platform_summary = top_group(filtered, "Platform").head(10)
    if not platform_summary.empty:
        fig = px.pie(platform_summary, names="Platform", values="transactions", title="Platform Share")
        st.plotly_chart(fig, use_container_width=True)

with col5:
    account_summary = top_group(filtered, "Account Type")
    if not account_summary.empty:
        fig = px.pie(account_summary, names="Account Type", values="transactions", title="Account Type Mix")
        st.plotly_chart(fig, use_container_width=True)

# Risk overview
st.subheader("Risk Overview")

col6, col7 = st.columns(2)

with col6:
    if not ms.empty:
        fig = px.bar(ms, x="period", y="risk_transactions", title="Risk Trend by Month")
        st.plotly_chart(fig, use_container_width=True)

with col7:
    if not ms.empty:
        fig = px.bar(ms, x="period", y="canceled_transactions", title="Canceled Trend by Month")
        st.plotly_chart(fig, use_container_width=True)

# Period comparison
st.subheader("Period Comparison")

enable_compare = st.checkbox("Aktifkan perbandingan periode", value=False)

if enable_compare and "Transaction Date" in filtered.columns and filtered["Transaction Date"].notna().any():
    min_compare_dt = filtered["Transaction Date"].min().date()
    max_compare_dt = filtered["Transaction Date"].max().date()

    a, b = st.columns(2)

    with a:
        period_1_range = st.date_input(
            "Period 1",
            value=[min_compare_dt, max_compare_dt],
            min_value=min_compare_dt,
            max_value=max_compare_dt,
            key="exec_p1"
        )

    with b:
        period_2_range = st.date_input(
            "Period 2",
            value=[min_compare_dt, max_compare_dt],
            min_value=min_compare_dt,
            max_value=max_compare_dt,
            key="exec_p2"
        )

    if isinstance(period_1_range, (list, tuple)) and len(period_1_range) == 2 and isinstance(period_2_range, (list, tuple)) and len(period_2_range) == 2:
        p1_start, p1_end = period_1_range
        p2_start, p2_end = period_2_range

        period_1_df = get_period_df(filtered, p1_start, p1_end)
        period_2_df = get_period_df(filtered, p2_start, p2_end)

        p1 = summarize_period(period_1_df)
        p2 = summarize_period(period_2_df)

        comparison_df = pd.DataFrame([
            {"Metric": "Total Transactions", "Period 1": p1["total_transactions"], "Period 2": p2["total_transactions"]},
            {"Metric": "Total Amount", "Period 1": p1["total_amount"], "Period 2": p2["total_amount"]},
            {"Metric": "Avg Amount", "Period 1": p1["avg_amount"], "Period 2": p2["avg_amount"]},
            {"Metric": "Success Rate (%)", "Period 1": p1["success_rate_pct"], "Period 2": p2["success_rate_pct"]},
            {"Metric": "Cancel Rate (%)", "Period 1": p1["cancel_rate_pct"], "Period 2": p2["cancel_rate_pct"]},
            {"Metric": "Risk Transactions", "Period 1": p1["risk_transactions"], "Period 2": p2["risk_transactions"]},
        ])

        comparison_df["Diff"] = comparison_df["Period 2"] - comparison_df["Period 1"]
        comparison_df["% Change"] = comparison_df.apply(
            lambda row: safe_pct_change(row["Period 2"], row["Period 1"]), axis=1
        )

        st.dataframe(comparison_df, use_container_width=True)

# Strategic insights
st.subheader("Strategic Insights")
for i, insight in enumerate(build_auto_insights(filtered), start=1):
    st.write(f"{i}. {insight}")

# Ringkasan tabel
with st.expander("Executive Summary Tables"):
    col8, col9, col10 = st.columns(3)

    with col8:
        st.write("Top Countries")
        st.dataframe(top_group(filtered, "Recipient Country").head(10), use_container_width=True)

    with col9:
        st.write("Top Platforms")
        st.dataframe(top_group(filtered, "Platform").head(10), use_container_width=True)

    with col10:
        st.write("Account Type")
        st.dataframe(top_group(filtered, "Account Type").head(10), use_container_width=True)