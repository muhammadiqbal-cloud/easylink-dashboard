import plotly.express as px
import streamlit as st

from utils import (
    prepare_data,
    format_number,
    format_currency,
    top_group,
    monthly_summary,
    convert_df_to_csv,
    apply_safe_date_filter,
    repeat_vs_new_summary,
    customer_segments,
    platform_monthly_growth,
    country_monthly_growth,
    drop_detection,
    voucher_promo_summary,
    build_marketing_advanced_insights,
)

st.set_page_config(page_title="Marketing Dashboard", layout="wide")
st.title("Marketing Dashboard")

df = prepare_data()
if df.empty:
    st.warning("Data tidak tersedia.")
    st.stop()

filtered = df.copy()

# =========================
# SIDEBAR FILTER
# =========================
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

filtered = apply_safe_date_filter(
    filtered,
    label="Custom Date",
    key="marketing_date_range"
)

# =========================
# KPI
# =========================
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

# =========================
# CHANNEL PERFORMANCE
# =========================
st.subheader("Channel Performance")

col1, col2 = st.columns(2)

platform_summary = top_group(filtered, "Platform").head(10)

with col1:
    if not platform_summary.empty:
        fig = px.bar(platform_summary, x="Platform", y="transactions", title="Transactions by Platform")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    if not platform_summary.empty and "total_amount" in platform_summary.columns:
        fig = px.bar(platform_summary, x="Platform", y="total_amount", title="Amount by Platform")
        st.plotly_chart(fig, use_container_width=True)

if not platform_summary.empty and "total_amount" in platform_summary.columns:
    platform_perf = platform_summary.copy()
    platform_perf["avg_value_per_tx"] = platform_perf["total_amount"] / platform_perf["transactions"]
    st.dataframe(platform_perf, use_container_width=True)

# =========================
# MARKET OPPORTUNITY
# =========================
st.subheader("Market Opportunity")

col3, col4 = st.columns(2)

country_summary = top_group(filtered, "Recipient Country").head(10)
purpose_summary = top_group(filtered, "Purpose").head(10)

with col3:
    if not country_summary.empty:
        fig = px.bar(country_summary, x="Recipient Country", y="transactions", title="Top Recipient Country")
        st.plotly_chart(fig, use_container_width=True)

with col4:
    if not purpose_summary.empty:
        fig = px.bar(purpose_summary, x="Purpose", y="transactions", title="Purpose Distribution")
        st.plotly_chart(fig, use_container_width=True)

country_growth = country_monthly_growth(filtered)
if not country_growth.empty:
    latest_country_growth = (
        country_growth.dropna(subset=["growth_pct"])
        .sort_values("growth_pct", ascending=False)
        .head(10)
    )
    if not latest_country_growth.empty:
        st.write("Top Growing Countries")
        st.dataframe(latest_country_growth[["Recipient Country", "period", "transactions", "growth_pct"]], use_container_width=True)

# =========================
# CUSTOMER BEHAVIOR
# =========================
st.subheader("Customer Behavior")

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

repeat_new = repeat_vs_new_summary(filtered)
if not repeat_new.empty:
    col8, col9 = st.columns(2)

    with col8:
        fig = px.pie(repeat_new, names="segment", values="users", title="New vs Occasional vs Loyal Users")
        st.plotly_chart(fig, use_container_width=True)

    with col9:
        seg_detail = customer_segments(filtered)
        if not seg_detail.empty:
            seg_summary = (
                seg_detail.groupby("segment", dropna=False)
                .agg(
                    users=("Name", "count"),
                    total_transactions=("transactions", "sum"),
                    total_amount=("total_amount", "sum")
                )
                .reset_index()
            )
            st.dataframe(seg_summary, use_container_width=True)

# =========================
# GROWTH & DROP DETECTION
# =========================
st.subheader("Growth & Drop Detection")

ms = monthly_summary(filtered)
if not ms.empty:
    col10, col11 = st.columns(2)

    with col10:
        fig = px.line(ms, x="period", y="transactions", markers=True, title="Monthly Transactions")
        st.plotly_chart(fig, use_container_width=True)

    with col11:
        fig = px.line(ms, x="period", y="total_amount", markers=True, title="Monthly Amount")
        st.plotly_chart(fig, use_container_width=True)

platform_growth = platform_monthly_growth(filtered)
if not platform_growth.empty:
    latest_platform_growth = (
        platform_growth.dropna(subset=["growth_pct"])
        .sort_values("growth_pct", ascending=False)
        .head(10)
    )
    if not latest_platform_growth.empty:
        st.write("Top Growing Platforms")
        st.dataframe(latest_platform_growth[["Platform", "period", "transactions", "growth_pct"]], use_container_width=True)

drops = drop_detection(filtered, threshold=-30)
if not drops.empty:
    st.warning("Detected significant monthly drops")
    st.dataframe(drops[["period", "transactions", "growth_pct"]], use_container_width=True)

# =========================
# VOUCHER & PROMO ANALYSIS
# =========================
st.subheader("Voucher & Promo Analysis")

promo_data = voucher_promo_summary(filtered)
voucher_col = promo_data.get("voucher_col")
promo_col = promo_data.get("promo_col")
discount_col = promo_data.get("discount_col")
voucher_usage = promo_data.get("voucher_usage", None)
promo_usage = promo_data.get("promo_usage", None)
promo_vs_nonpromo = promo_data.get("promo_vs_nonpromo", None)

if not voucher_col and not promo_col:
    st.info("Kolom voucher/promo belum ditemukan. Tambahkan kolom seperti 'Voucher Code', 'Promo Code', atau 'Promo Name'.")
else:
    st.write(f"Voucher column: {voucher_col if voucher_col else '-'}")
    st.write(f"Promo column: {promo_col if promo_col else '-'}")
    st.write(f"Discount column: {discount_col if discount_col else '-'}")

    col12, col13 = st.columns(2)

    with col12:
        if voucher_usage is not None and not voucher_usage.empty:
            fig = px.bar(voucher_usage.head(10), x=voucher_col, y="transactions", title="Top Voucher Usage")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(voucher_usage.head(20), use_container_width=True)

    with col13:
        if promo_usage is not None and not promo_usage.empty:
            fig = px.bar(promo_usage.head(10), x=promo_col, y="transactions", title="Top Promo Usage")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(promo_usage.head(20), use_container_width=True)

    if promo_vs_nonpromo is not None and not promo_vs_nonpromo.empty:
        col14, col15 = st.columns(2)

        with col14:
            fig = px.pie(promo_vs_nonpromo, names="promo_flag", values="transactions", title="Promo vs Non-Promo Transactions")
            st.plotly_chart(fig, use_container_width=True)

        with col15:
            if "total_amount" in promo_vs_nonpromo.columns:
                fig = px.bar(promo_vs_nonpromo, x="promo_flag", y="total_amount", title="Promo vs Non-Promo Amount")
                st.plotly_chart(fig, use_container_width=True)

        st.dataframe(promo_vs_nonpromo, use_container_width=True)

# =========================
# MARKETING INSIGHTS
# =========================
st.subheader("Marketing Advanced Insights")
for i, insight in enumerate(build_marketing_advanced_insights(filtered), start=1):
    st.write(f"{i}. {insight}")

# =========================
# DETAIL TABLES
# =========================
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

    st.dataframe(display_filtered.head(200), use_container_width=True)

csv_data = convert_df_to_csv(filtered)
st.download_button(
    label="Download marketing data as CSV",
    data=csv_data,
    file_name="marketing_filtered_data.csv",
    mime="text/csv",
    key="download_marketing_csv",
    on_click="ignore",
)