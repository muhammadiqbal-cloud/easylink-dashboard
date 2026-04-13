import pandas as pd
import streamlit as st
import plotly.express as px
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Remittance Dashboard", layout="wide")


def format_number(x):
    try:
        if pd.isna(x):
            return "0"
        return f"{x:,.0f}".replace(",", ".")
    except Exception:
        return x


def format_currency(x):
    try:
        if pd.isna(x):
            return "Rp 0"
        return "Rp " + f"{x:,.0f}".replace(",", ".")
    except Exception:
        return x


def format_percent(x):
    try:
        if pd.isna(x):
            return "0%"
        return f"{x:.2f}%"
    except Exception:
        return x


# =========================
# LOAD DATA FROM GOOGLE SHEETS
# =========================
@st.cache_data(ttl=300)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)

    sheet_map = {
        "2023": 0,
        "2024": 1,
        "2025": 2,
        "2026": 3,
    }

    all_dfs = []

    for label, idx in sheet_map.items():
        try:
            df = conn.read(worksheet=idx, ttl=0)
            if df is not None and not df.empty:
                df["source_sheet"] = label
                all_dfs.append(df)
            else:
                st.warning(f"Sheet {label} kosong")
        except Exception as e:
            st.warning(f"Gagal membaca sheet {label}: {e}")

    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)

    return pd.DataFrame()
# =========================
# CLEANING
# =========================
def clean_data(df):
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    text_cols = [
        "Ref Id", "Remittance Channel", "Account Type", "Phone Number", "Email", "Name",
        "Status", "Amount Sent currency", "Recipient Gets currency", "Recipient Country",
        "Purpose", "Source of Funds", "Relationship", "Payment Method",
        "Merchant Id", "Sender region", "Sender's address city", "Recipient's name",
        "Platform", "source_sheet"
    ]

    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"nan": "", "None": ""})

    numeric_cols = ["Amount Sent", "Recipient Gets amount", "Admin Fee (IDR)"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Transaction Date" in df.columns:
        df["Transaction Date"] = pd.to_datetime(
            df["Transaction Date"],
            format="%d-%m-%Y %H:%M:%S",
            errors="coerce"
        )

    if "Status" in df.columns:
        df["Status_clean"] = df["Status"].astype(str).str.lower().str.strip()
    else:
        df["Status_clean"] = ""

    fill_unknown_cols = [
        "Recipient Country", "Platform", "Payment Method",
        "Purpose", "Relationship", "Name", "source_sheet", "Account Type"
    ]

    for col in fill_unknown_cols:
        if col in df.columns:
            df[col] = df[col].replace("", "Unknown").fillna("Unknown")

    if "Recipient Country" in df.columns:
        df["Recipient Country"] = df["Recipient Country"].replace({
            "USA": "United States",
            "US": "United States",
            "UK": "United Kingdom",
            "UAE": "United Arab Emirates"
        })

    if "Transaction Date" in df.columns:
        df["Date"] = df["Transaction Date"].dt.date
        df["Hour"] = df["Transaction Date"].dt.hour
        df["Year"] = df["Transaction Date"].dt.year
        df["Month"] = df["Transaction Date"].dt.month

    return df


# =========================
# RISK FLAGS
# =========================
def make_risk_flags(df):
    df = df.copy()

    df["flag_canceled"] = df["Status_clean"].str.contains("cancel", na=False)

    df["flag_repeat_phone"] = False
    if "Phone Number" in df.columns:
        phone_counts = df["Phone Number"].value_counts()
        repeat_phones = phone_counts[phone_counts > 1].index
        df["flag_repeat_phone"] = df["Phone Number"].isin(repeat_phones)

    df["flag_repeat_email"] = False
    if "Email" in df.columns:
        email_counts = df["Email"].value_counts()
        repeat_emails = email_counts[email_counts > 1].index
        df["flag_repeat_email"] = df["Email"].isin(repeat_emails)

    df["flag_high_amount"] = False
    if "Amount Sent" in df.columns and df["Amount Sent"].notna().sum() > 0:
        threshold = df["Amount Sent"].quantile(0.95)
        df["flag_high_amount"] = df["Amount Sent"] >= threshold

    flag_cols = [
        "flag_canceled",
        "flag_repeat_phone",
        "flag_repeat_email",
        "flag_high_amount"
    ]
    df["risk_score"] = df[flag_cols].sum(axis=1)

    def build_risk_reason(row):
        reasons = []

        if row.get("flag_canceled", False):
            reasons.append("Canceled transaction")
        if row.get("flag_repeat_phone", False):
            reasons.append("Repeated phone number")
        if row.get("flag_repeat_email", False):
            reasons.append("Repeated email")
        if row.get("flag_high_amount", False):
            reasons.append("High transaction amount")

        return ", ".join(reasons) if reasons else "No risk"

    def build_risk_severity(score):
        if score >= 3:
            return "High"
        elif score == 2:
            return "Medium"
        elif score == 1:
            return "Low"
        return "No Risk"

    def build_risk_category(row):
        categories = []

        if row.get("flag_canceled", False):
            categories.append("Operational")
        if row.get("flag_repeat_phone", False) or row.get("flag_repeat_email", False):
            categories.append("Behavioral")
        if row.get("flag_high_amount", False):
            categories.append("Financial")

        return ", ".join(sorted(set(categories))) if categories else "None"

    df["risk_reason"] = df.apply(build_risk_reason, axis=1)
    df["risk_severity"] = df["risk_score"].apply(build_risk_severity)
    df["risk_category"] = df.apply(build_risk_category, axis=1)

    return df


# =========================
# HELPER
# =========================
def top_group(df, col):
    if col not in df.columns:
        return pd.DataFrame()

    agg_dict = {
        "transactions": ("Id", "count") if "Id" in df.columns else (col, "count")
    }

    if "Amount Sent" in df.columns:
        agg_dict["total_amount"] = ("Amount Sent", "sum")

    out = (
        df.groupby(col, dropna=False)
        .agg(**agg_dict)
        .reset_index()
    )

    sort_cols = ["transactions"]
    ascending_vals = [False]

    if "total_amount" in out.columns:
        sort_cols.append("total_amount")
        ascending_vals.append(False)

    return out.sort_values(sort_cols, ascending=ascending_vals)


def summarize_period(df_period):
    summary = {
        "total_transactions": len(df_period),
        "total_amount": df_period["Amount Sent"].sum() if "Amount Sent" in df_period.columns else 0,
        "avg_amount": df_period["Amount Sent"].mean() if "Amount Sent" in df_period.columns and len(df_period) > 0 else 0,
        "canceled_transactions": df_period["flag_canceled"].sum() if "flag_canceled" in df_period.columns else 0,
        "risk_transactions": (df_period["risk_score"] > 0).sum() if "risk_score" in df_period.columns else 0,
    }

    if summary["total_transactions"] > 0:
        summary["cancel_rate_pct"] = round(
            summary["canceled_transactions"] / summary["total_transactions"] * 100, 2
        )
    else:
        summary["cancel_rate_pct"] = 0

    return summary


def get_period_df(df_source, start_date, end_date):
    return df_source[
        (df_source["Transaction Date"] >= pd.to_datetime(start_date)) &
        (df_source["Transaction Date"] < pd.to_datetime(end_date) + pd.Timedelta(days=1))
    ].copy()


def safe_pct_change(current, previous):
    if previous in [0, None] or pd.isna(previous):
        return None
    return round((current - previous) / previous * 100, 2)


def build_auto_insights(filtered):
    insights = []

    total_tx = len(filtered)
    total_amount = filtered["Amount Sent"].sum() if "Amount Sent" in filtered.columns else 0
    cancel_count = filtered["flag_canceled"].sum() if "flag_canceled" in filtered.columns else 0
    cancel_rate = (cancel_count / total_tx * 100) if total_tx > 0 else 0

    insights.append(f"Total transaksi pada filter saat ini: {format_number(total_tx)}")
    if "Amount Sent" in filtered.columns:
        insights.append(f"Total nominal terkirim: {format_currency(total_amount)}")
    insights.append(f"Persentase transaksi canceled: {format_percent(cancel_rate)}")

    if "Account Type" in filtered.columns and not filtered.empty:
        account_summary = top_group(filtered, "Account Type")
        if not account_summary.empty:
            top_account = account_summary.iloc[0]
            insights.append(
                f"Account type dominan: {top_account['Account Type']} "
                f"({format_number(top_account['transactions'])} transaksi)"
            )

    if "Recipient Country" in filtered.columns and not filtered.empty:
        country_summary = top_group(filtered, "Recipient Country")
        if not country_summary.empty:
            top_country = country_summary.iloc[0]
            insights.append(
                f"Negara tujuan terbesar: {top_country['Recipient Country']} "
                f"({format_number(top_country['transactions'])} transaksi)"
            )

    if "Platform" in filtered.columns and not filtered.empty:
        platform_summary = top_group(filtered, "Platform")
        if not platform_summary.empty:
            top_platform = platform_summary.iloc[0]
            insights.append(
                f"Platform paling dominan: {top_platform['Platform']} "
                f"({format_number(top_platform['transactions'])} transaksi)"
            )

    if "Name" in filtered.columns and not filtered.empty:
        sender_summary = top_group(filtered, "Name")
        if not sender_summary.empty:
            top_sender = sender_summary.iloc[0]
            insights.append(
                f"Sender paling aktif: {top_sender['Name']} "
                f"({format_number(top_sender['transactions'])} transaksi)"
            )

    if "source_sheet" in filtered.columns and not filtered.empty:
        year_summary = top_group(filtered, "source_sheet")
        if not year_summary.empty:
            top_year = year_summary.iloc[0]
            insights.append(
                f"Tab tahun paling aktif: {top_year['source_sheet']} "
                f"({format_number(top_year['transactions'])} transaksi)"
            )

    risk_count = (filtered["risk_score"] > 0).sum() if "risk_score" in filtered.columns else 0
    insights.append(f"Jumlah transaksi yang memiliki risk flag: {format_number(risk_count)}")

    return insights


# =========================
# APP START
# =========================
st.title("Transaction Report Easylink")

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"Gagal membaca Google Sheets: {e}")
    st.stop()

if df_raw is None or df_raw.empty:
    st.warning("Data di Google Sheets kosong atau semua sheet tahun tidak terbaca.")
    st.stop()

col_a, col_b = st.columns([1, 6])
with col_a:
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

df = clean_data(df_raw)
df = make_risk_flags(df)
filtered = df.copy()

# =========================
# SIDEBAR FILTERS
# =========================
st.sidebar.header("Filter Dashboard")

if "source_sheet" in filtered.columns:
    source_options = sorted(filtered["source_sheet"].dropna().unique().tolist())
    selected_source = st.sidebar.multiselect(
        "Tahun Data (Tab Sheet)",
        source_options,
        default=source_options
    )
    filtered = filtered[filtered["source_sheet"].isin(selected_source)]

if "Account Type" in filtered.columns:
    account_options = sorted(filtered["Account Type"].dropna().unique().tolist())
    selected_account = st.sidebar.multiselect(
        "Account Type",
        account_options,
        default=account_options
    )
    filtered = filtered[filtered["Account Type"].isin(selected_account)]

st.sidebar.subheader("Filter Tanggal")

if "Transaction Date" in filtered.columns and filtered["Transaction Date"].notna().any():
    min_dt = filtered["Transaction Date"].min()
    max_dt = filtered["Transaction Date"].max()

    filter_mode = st.sidebar.radio(
        "Mode Filter Tanggal",
        ["Semua Data", "Periode Custom", "Per Bulan", "Per Tahun"]
    )

    if filter_mode == "Periode Custom":
        date_range = st.sidebar.date_input(
            "Pilih range tanggal",
            value=[min_dt.date(), max_dt.date()],
            min_value=min_dt.date(),
            max_value=max_dt.date()
        )

        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                (filtered["Transaction Date"] >= pd.to_datetime(start_date)) &
                (filtered["Transaction Date"] < pd.to_datetime(end_date) + pd.Timedelta(days=1))
            ]

    elif filter_mode == "Per Bulan":
        available_years = sorted(
            filtered["Transaction Date"].dt.year.dropna().unique().astype(int).tolist()
        )
        selected_year = st.sidebar.selectbox("Pilih Tahun", available_years)

        month_map = {
            "Januari": 1, "Februari": 2, "Maret": 3, "April": 4,
            "Mei": 5, "Juni": 6, "Juli": 7, "Agustus": 8,
            "September": 9, "Oktober": 10, "November": 11, "Desember": 12
        }
        selected_month_name = st.sidebar.selectbox("Pilih Bulan", list(month_map.keys()))
        selected_month = month_map[selected_month_name]

        filtered = filtered[
            (filtered["Transaction Date"].dt.year == selected_year) &
            (filtered["Transaction Date"].dt.month == selected_month)
        ]

    elif filter_mode == "Per Tahun":
        available_years = sorted(
            filtered["Transaction Date"].dt.year.dropna().unique().astype(int).tolist()
        )
        selected_year = st.sidebar.selectbox("Pilih Tahun Penuh", available_years)
        filtered = filtered[filtered["Transaction Date"].dt.year == selected_year]

if "Recipient Country" in filtered.columns:
    country_options = sorted(filtered["Recipient Country"].dropna().unique().tolist())
    selected_country = st.sidebar.multiselect(
        "Recipient Country",
        country_options,
        default=country_options
    )
    filtered = filtered[filtered["Recipient Country"].isin(selected_country)]

if "Platform" in filtered.columns:
    platform_options = sorted(filtered["Platform"].dropna().unique().tolist())
    selected_platform = st.sidebar.multiselect(
        "Platform",
        platform_options,
        default=platform_options
    )
    filtered = filtered[filtered["Platform"].isin(selected_platform)]

if "Status" in filtered.columns:
    status_options = sorted(filtered["Status"].dropna().unique().tolist())
    selected_status = st.sidebar.multiselect(
        "Status",
        status_options,
        default=status_options
    )
    filtered = filtered[filtered["Status"].isin(selected_status)]

if "Name" in filtered.columns:
    sender_options = sorted(filtered["Name"].dropna().unique().tolist())
    selected_sender = st.sidebar.multiselect(
        "Sender Name",
        sender_options,
        default=sender_options
    )
    filtered = filtered[filtered["Name"].isin(selected_sender)]

# =========================
# PERIOD COMPARISON SIDEBAR
# =========================
st.sidebar.subheader("Perbandingan Periode")

enable_period_compare = st.sidebar.checkbox("Aktifkan Perbandingan Periode", value=False)

period_1_df = pd.DataFrame()
period_2_df = pd.DataFrame()

if enable_period_compare and "Transaction Date" in filtered.columns and filtered["Transaction Date"].notna().any():
    min_compare_dt = filtered["Transaction Date"].min().date()
    max_compare_dt = filtered["Transaction Date"].max().date()

    st.sidebar.markdown("**Period 1**")
    period_1_range = st.sidebar.date_input(
        "Pilih Period 1",
        value=[min_compare_dt, max_compare_dt],
        min_value=min_compare_dt,
        max_value=max_compare_dt,
        key="period_1_range"
    )

    st.sidebar.markdown("**Period 2**")
    period_2_range = st.sidebar.date_input(
        "Pilih Period 2",
        value=[min_compare_dt, max_compare_dt],
        min_value=min_compare_dt,
        max_value=max_compare_dt,
        key="period_2_range"
    )

    if isinstance(period_1_range, (list, tuple)) and len(period_1_range) == 2:
        p1_start, p1_end = period_1_range
        period_1_df = get_period_df(filtered, p1_start, p1_end)

    if isinstance(period_2_range, (list, tuple)) and len(period_2_range) == 2:
        p2_start, p2_end = period_2_range
        period_2_df = get_period_df(filtered, p2_start, p2_end)

# =========================
# KPI
# =========================
total_tx = len(filtered)
total_amount = filtered["Amount Sent"].sum() if "Amount Sent" in filtered.columns else 0
avg_amount = filtered["Amount Sent"].mean() if "Amount Sent" in filtered.columns else 0
cancel_count = filtered["flag_canceled"].sum() if "flag_canceled" in filtered.columns else 0
cancel_rate = (cancel_count / total_tx * 100) if total_tx > 0 else 0
risk_count = (filtered["risk_score"] > 0).sum() if "risk_score" in filtered.columns else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Transaksi", format_number(total_tx))
c2.metric("Total Amount Sent", format_currency(total_amount))
c3.metric("Rata-rata Amount", format_currency(avg_amount))
c4.metric("Canceled Rate", format_percent(cancel_rate))
c5.metric("Risk Transactions", format_number(risk_count))

# =========================
# PERIOD COMPARISON OUTPUT
# =========================
if enable_period_compare:
    st.subheader("Perbandingan Periode")

    if period_1_df.empty or period_2_df.empty:
        st.warning("Pilih dua periode yang valid.")
    else:
        period_1_summary = summarize_period(period_1_df)
        period_2_summary = summarize_period(period_2_df)

        comparison_df = pd.DataFrame([
            {
                "Metric": "Total Transaksi",
                "Period 1": period_1_summary["total_transactions"],
                "Period 2": period_2_summary["total_transactions"],
            },
            {
                "Metric": "Total Amount",
                "Period 1": period_1_summary["total_amount"],
                "Period 2": period_2_summary["total_amount"],
            },
            {
                "Metric": "Avg Amount",
                "Period 1": period_1_summary["avg_amount"],
                "Period 2": period_2_summary["avg_amount"],
            },
            {
                "Metric": "Cancel Rate (%)",
                "Period 1": period_1_summary["cancel_rate_pct"],
                "Period 2": period_2_summary["cancel_rate_pct"],
            },
            {
                "Metric": "Risk Transactions",
                "Period 1": period_1_summary["risk_transactions"],
                "Period 2": period_2_summary["risk_transactions"],
            }
        ])

        comparison_df["Diff"] = comparison_df["Period 2"] - comparison_df["Period 1"]
        comparison_df["% Change"] = comparison_df.apply(
            lambda row: safe_pct_change(row["Period 2"], row["Period 1"]),
            axis=1
        )

        display_df = comparison_df.copy().astype(object)

        amount_metrics = ["Total Amount", "Avg Amount"]

        for metric in amount_metrics:
            mask = display_df["Metric"] == metric
            display_df.loc[mask, "Period 1"] = display_df.loc[mask, "Period 1"].apply(format_currency)
            display_df.loc[mask, "Period 2"] = display_df.loc[mask, "Period 2"].apply(format_currency)
            display_df.loc[mask, "Diff"] = display_df.loc[mask, "Diff"].apply(format_currency)

        non_amount_mask = ~display_df["Metric"].isin(amount_metrics)
        display_df.loc[non_amount_mask, "Period 1"] = display_df.loc[non_amount_mask, "Period 1"].apply(format_number)
        display_df.loc[non_amount_mask, "Period 2"] = display_df.loc[non_amount_mask, "Period 2"].apply(format_number)
        display_df.loc[non_amount_mask, "Diff"] = display_df.loc[non_amount_mask, "Diff"].apply(format_number)

        display_df["% Change"] = display_df["% Change"].apply(
            lambda x: "-" if x is None else f"{x:.2f}%"
        )

        st.dataframe(display_df, use_container_width=True)

        chart_df = comparison_df.melt(
            id_vars="Metric",
            value_vars=["Period 1", "Period 2"],
            var_name="Period",
            value_name="Value"
        )

        fig = px.bar(
            chart_df,
            x="Metric",
            y="Value",
            color="Period",
            barmode="group",
            title="Perbandingan KPI Antar Periode"
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Perbandingan Negara Tujuan")

        p1_country = top_group(period_1_df, "Recipient Country")
        p2_country = top_group(period_2_df, "Recipient Country")

        if not p1_country.empty or not p2_country.empty:
            merged_country = pd.merge(
                p1_country,
                p2_country,
                on="Recipient Country",
                how="outer",
                suffixes=("_p1", "_p2")
            ).fillna(0)

            merged_country["diff"] = merged_country["transactions_p2"] - merged_country["transactions_p1"]

            display_country = merged_country.copy()
            for col in ["transactions_p1", "transactions_p2", "diff"]:
                if col in display_country.columns:
                    display_country[col] = display_country[col].apply(format_number)
            for col in ["total_amount_p1", "total_amount_p2"]:
                if col in display_country.columns:
                    display_country[col] = display_country[col].apply(format_currency)

            st.dataframe(display_country.sort_values("Recipient Country"), use_container_width=True)

# =========================
# DEBUG FILTER
# =========================
with st.expander("Debug Filter"):
    st.write("Total raw data:", len(df))
    st.write("Total setelah filter:", len(filtered))

    if "source_sheet" in df.columns:
        st.write("Jumlah transaksi per source_sheet (raw):")
        st.dataframe(
            df["source_sheet"]
            .value_counts(dropna=False)
            .rename_axis("source_sheet")
            .reset_index(name="transactions"),
            use_container_width=True
        )

    if "source_sheet" in filtered.columns:
        st.write("Jumlah transaksi per source_sheet (filtered):")
        st.dataframe(
            filtered["source_sheet"]
            .value_counts(dropna=False)
            .rename_axis("source_sheet")
            .reset_index(name="transactions"),
            use_container_width=True
        )

    if "Account Type" in df.columns:
        st.write("Jumlah transaksi per Account Type (raw):")
        st.dataframe(
            df["Account Type"]
            .value_counts(dropna=False)
            .rename_axis("Account Type")
            .reset_index(name="transactions"),
            use_container_width=True
        )

    if "Account Type" in filtered.columns:
        st.write("Jumlah transaksi per Account Type (filtered):")
        st.dataframe(
            filtered["Account Type"]
            .value_counts(dropna=False)
            .rename_axis("Account Type")
            .reset_index(name="transactions"),
            use_container_width=True
        )

    if "Status" in df.columns:
        st.write("Jumlah transaksi per status (raw):")
        st.dataframe(
            df["Status"]
            .value_counts(dropna=False)
            .rename_axis("Status")
            .reset_index(name="transactions"),
            use_container_width=True
        )

    if "Status" in filtered.columns:
        st.write("Jumlah transaksi per status (filtered):")
        st.dataframe(
            filtered["Status"]
            .value_counts(dropna=False)
            .rename_axis("Status")
            .reset_index(name="transactions"),
            use_container_width=True
        )

# =========================
# INSIGHT OTOMATIS
# =========================
st.subheader("Insight Otomatis")
insights = build_auto_insights(filtered)
for i, insight in enumerate(insights, start=1):
    st.write(f"{i}. {insight}")

# =========================
# COMPARISON PERSONAL VS BUSINESS
# =========================
st.subheader("Perbandingan PERSONAL vs BUSINESS")

if "Account Type" in filtered.columns and not filtered.empty:
    account_compare = (
        filtered.groupby("Account Type", dropna=False)
        .agg(
            total_transactions=("Id", "count") if "Id" in filtered.columns else ("Account Type", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in filtered.columns else ("Account Type", "count"),
            avg_amount=("Amount Sent", "mean") if "Amount Sent" in filtered.columns else ("Account Type", "count"),
            canceled_transactions=("flag_canceled", "sum") if "flag_canceled" in filtered.columns else ("Account Type", "count"),
            risk_transactions=("risk_score", lambda x: (x > 0).sum()) if "risk_score" in filtered.columns else ("Account Type", "count")
        )
        .reset_index()
    )

    if "total_transactions" in account_compare.columns:
        account_compare["cancel_rate_pct"] = (
            account_compare["canceled_transactions"] / account_compare["total_transactions"] * 100
        ).round(2)

    display_account_compare = account_compare.copy()
    if "total_transactions" in display_account_compare.columns:
        display_account_compare["total_transactions"] = display_account_compare["total_transactions"].apply(format_number)
    if "total_amount" in display_account_compare.columns:
        display_account_compare["total_amount"] = display_account_compare["total_amount"].apply(format_currency)
    if "avg_amount" in display_account_compare.columns:
        display_account_compare["avg_amount"] = display_account_compare["avg_amount"].apply(format_currency)
    if "canceled_transactions" in display_account_compare.columns:
        display_account_compare["canceled_transactions"] = display_account_compare["canceled_transactions"].apply(format_number)
    if "risk_transactions" in display_account_compare.columns:
        display_account_compare["risk_transactions"] = display_account_compare["risk_transactions"].apply(format_number)
    if "cancel_rate_pct" in display_account_compare.columns:
        display_account_compare["cancel_rate_pct"] = display_account_compare["cancel_rate_pct"].apply(format_percent)

    st.dataframe(display_account_compare, use_container_width=True)
else:
    st.write("Data account type tidak tersedia.")

# =========================
# CHARTS
# =========================
col1, col2 = st.columns(2)

with col1:
    st.subheader("Top Recipient Country")
    country_summary = top_group(filtered, "Recipient Country").head(10)
    if not country_summary.empty:
        fig = px.bar(
            country_summary,
            x="Recipient Country",
            y="transactions",
            hover_data=[c for c in ["total_amount"] if c in country_summary.columns]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Data tidak tersedia.")

with col2:
    st.subheader("Top Platform")
    platform_summary = top_group(filtered, "Platform").head(10)
    if not platform_summary.empty:
        fig = px.pie(
            platform_summary,
            names="Platform",
            values="transactions"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Data tidak tersedia.")

col3, col4 = st.columns(2)

with col3:
    st.subheader("Top Payment Method")
    payment_summary = top_group(filtered, "Payment Method").head(10)
    if not payment_summary.empty:
        fig = px.bar(
            payment_summary,
            x="Payment Method",
            y="transactions",
            hover_data=[c for c in ["total_amount"] if c in payment_summary.columns]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Data tidak tersedia.")

with col4:
    st.subheader("Top Sender")
    sender_summary = top_group(filtered, "Name").head(10)
    if not sender_summary.empty:
        fig = px.bar(
            sender_summary,
            x="Name",
            y="transactions",
            hover_data=[c for c in ["total_amount"] if c in sender_summary.columns]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Data tidak tersedia.")

st.subheader("Distribusi Purpose")
purpose_summary = top_group(filtered, "Purpose").head(10)
if not purpose_summary.empty:
    fig = px.bar(
        purpose_summary,
        x="Purpose",
        y="transactions",
        hover_data=[c for c in ["total_amount"] if c in purpose_summary.columns]
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.write("Data tidak tersedia.")

st.subheader("Distribusi Account Type")
account_summary = top_group(filtered, "Account Type")
if not account_summary.empty:
    fig = px.pie(
        account_summary,
        names="Account Type",
        values="transactions"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.write("Data account type tidak tersedia.")

if "Account Type" in filtered.columns and not filtered.empty:
    account_bar = top_group(filtered, "Account Type")
    if not account_bar.empty:
        fig = px.bar(
            account_bar,
            x="Account Type",
            y="transactions",
            hover_data=[c for c in ["total_amount"] if c in account_bar.columns]
        )
        st.plotly_chart(fig, use_container_width=True)

if "source_sheet" in filtered.columns:
    st.subheader("Distribusi Data per Tab Tahun")
    source_summary = top_group(filtered, "source_sheet")
    if not source_summary.empty:
        fig = px.bar(
            source_summary,
            x="source_sheet",
            y="transactions",
            hover_data=[c for c in ["total_amount"] if c in source_summary.columns]
        )
        st.plotly_chart(fig, use_container_width=True)

# =========================
# GEOGRAPHY MAP
# =========================
st.subheader("Geografi Transaksi (Negara Tujuan)")

if "Recipient Country" in filtered.columns and not filtered.empty:
    geo_df = (
        filtered.groupby("Recipient Country", dropna=False)
        .agg(
            transactions=("Id", "count") if "Id" in filtered.columns else ("Recipient Country", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in filtered.columns else ("Recipient Country", "count")
        )
        .reset_index()
    )

    if not geo_df.empty:
        fig = px.choropleth(
            geo_df,
            locations="Recipient Country",
            locationmode="country names",
            color="transactions",
            hover_name="Recipient Country",
            hover_data=["total_amount"]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Data geografi tidak tersedia.")
else:
    st.write("Kolom Recipient Country tidak tersedia.")

# =========================
# TREND HARIAN
# =========================
st.subheader("Trend Harian")

if "Date" in filtered.columns and not filtered.empty:
    daily = (
        filtered.groupby("Date")
        .agg(
            transactions=("Id", "count") if "Id" in filtered.columns else ("Date", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in filtered.columns else ("Date", "count")
        )
        .reset_index()
        .sort_values("Date")
    )

    if not daily.empty:
        fig = px.line(
            daily,
            x="Date",
            y="transactions",
            markers=True,
            hover_data=[c for c in ["total_amount"] if c in daily.columns]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Data trend tidak tersedia.")
else:
    st.write("Kolom tanggal tidak tersedia.")

# =========================
# RISK TABLE
# =========================
st.subheader("Risk Transactions")

risk_cols = [
    "source_sheet", "Account Type", "Id", "Ref Id", "Transaction Date", "Name",
    "Phone Number", "Email", "Recipient Country", "Recipient's name",
    "Amount Sent", "Status",
    "risk_category", "risk_reason", "risk_severity", "risk_score",
    "flag_canceled", "flag_repeat_phone", "flag_repeat_email", "flag_high_amount"
]
risk_cols = [c for c in risk_cols if c in filtered.columns]

if "risk_score" in filtered.columns:
    risk_df = filtered[filtered["risk_score"] > 0][risk_cols].sort_values(
        by=["risk_score", "Amount Sent"] if "Amount Sent" in filtered.columns else ["risk_score"],
        ascending=[False, False] if "Amount Sent" in filtered.columns else [False]
    )
else:
    risk_df = pd.DataFrame()

display_risk_df = risk_df.copy()
if "Amount Sent" in display_risk_df.columns:
    display_risk_df["Amount Sent"] = display_risk_df["Amount Sent"].apply(format_currency)
if "risk_score" in display_risk_df.columns:
    display_risk_df["risk_score"] = display_risk_df["risk_score"].apply(format_number)

st.dataframe(display_risk_df, use_container_width=True)

# =========================
# FILTERED DATA
# =========================
st.subheader("Filtered Data")
display_filtered = filtered.copy()
if "Amount Sent" in display_filtered.columns:
    display_filtered["Amount Sent"] = display_filtered["Amount Sent"].apply(format_currency)
if "Recipient Gets amount" in display_filtered.columns:
    display_filtered["Recipient Gets amount"] = display_filtered["Recipient Gets amount"].apply(format_number)
if "Admin Fee (IDR)" in display_filtered.columns:
    display_filtered["Admin Fee (IDR)"] = display_filtered["Admin Fee (IDR)"].apply(format_currency)

st.dataframe(display_filtered, use_container_width=True)

# =========================
# DOWNLOAD CSV
# =========================
csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download filtered data as CSV",
    data=csv,
    file_name="filtered_remittance_data.csv",
    mime="text/csv"
)