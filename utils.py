import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection


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


@st.cache_data(ttl=300)
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl=0)
    if df is None:
        return pd.DataFrame()
    return df.copy()


def clean_numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.strip()
        .str.replace("Rp", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False),
        errors="coerce"
    )


def clean_data(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

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
            df[col] = df[col].replace({"nan": "", "None": "", "<NA>": ""})

    numeric_cols = ["Amount Sent", "Recipient Gets amount", "Admin Fee (IDR)"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    if "Transaction Date" in df.columns:
        tx = df["Transaction Date"].astype(str).str.strip()
        tx = tx.replace({
            "nan": None,
            "None": None,
            "<NA>": None,
            "NaT": None,
            "": None
        })

        parsed_dt = pd.to_datetime(
            tx,
            format="%d-%m-%Y %H:%M:%S",
            errors="coerce"
        )

        missing_mask = parsed_dt.isna()
        if missing_mask.any():
            parsed_dt.loc[missing_mask] = pd.to_datetime(
                tx.loc[missing_mask],
                errors="coerce",
                dayfirst=True
            )

        missing_mask = parsed_dt.isna()
        if missing_mask.any():
            parsed_dt.loc[missing_mask] = pd.to_datetime(
                tx.loc[missing_mask],
                errors="coerce"
            )

        df["Transaction Date"] = parsed_dt
        df["source_sheet"] = df["Transaction Date"].dt.year.astype("Int64").astype(str)
        df["source_sheet"] = df["source_sheet"].replace("<NA>", "Unknown")
        df["Date"] = df["Transaction Date"].dt.date
        df["Hour"] = df["Transaction Date"].dt.hour
        df["Year"] = df["Transaction Date"].dt.year
        df["Month"] = df["Transaction Date"].dt.month
        df["Month Name"] = df["Transaction Date"].dt.strftime("%b %Y")
    else:
        df["source_sheet"] = "Unknown"

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

    return df


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
        if score == 2:
            return "Medium"
        if score == 1:
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


def prepare_data():
    df_raw = load_data()
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()
    df = clean_data(df_raw)
    df = make_risk_flags(df)
    return df


def top_group(df, col):
    if col not in df.columns:
        return pd.DataFrame()

    agg_dict = {
        "transactions": ("Id", "count") if "Id" in df.columns else (col, "count")
    }

    if "Amount Sent" in df.columns:
        agg_dict["total_amount"] = ("Amount Sent", "sum")

    out = df.groupby(col, dropna=False).agg(**agg_dict).reset_index()

    sort_cols = ["transactions"]
    ascending_vals = [False]

    if "total_amount" in out.columns:
        sort_cols.append("total_amount")
        ascending_vals.append(False)

    return out.sort_values(sort_cols, ascending=ascending_vals)


def summarize_period(df_period):
    total_transactions = len(df_period)
    total_amount = df_period["Amount Sent"].sum() if "Amount Sent" in df_period.columns else 0
    avg_amount = df_period["Amount Sent"].mean() if "Amount Sent" in df_period.columns and total_transactions > 0 else 0
    canceled_transactions = df_period["flag_canceled"].sum() if "flag_canceled" in df_period.columns else 0
    risk_transactions = (df_period["risk_score"] > 0).sum() if "risk_score" in df_period.columns else 0
    success_transactions = total_transactions - canceled_transactions
    success_rate = (success_transactions / total_transactions * 100) if total_transactions > 0 else 0
    cancel_rate = (canceled_transactions / total_transactions * 100) if total_transactions > 0 else 0

    return {
        "total_transactions": total_transactions,
        "total_amount": total_amount,
        "avg_amount": avg_amount,
        "canceled_transactions": canceled_transactions,
        "risk_transactions": risk_transactions,
        "success_transactions": success_transactions,
        "success_rate_pct": round(success_rate, 2),
        "cancel_rate_pct": round(cancel_rate, 2),
    }


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

    if "Recipient Country" in filtered.columns and not filtered.empty:
        top_country = top_group(filtered, "Recipient Country")
        if not top_country.empty:
            row = top_country.iloc[0]
            insights.append(
                f"Negara tujuan terbesar: {row['Recipient Country']} ({format_number(row['transactions'])} transaksi)"
            )

    if "Platform" in filtered.columns and not filtered.empty:
        top_platform = top_group(filtered, "Platform")
        if not top_platform.empty:
            row = top_platform.iloc[0]
            insights.append(
                f"Platform dominan: {row['Platform']} ({format_number(row['transactions'])} transaksi)"
            )

    risk_count = (filtered["risk_score"] > 0).sum() if "risk_score" in filtered.columns else 0
    insights.append(f"Jumlah transaksi berisiko: {format_number(risk_count)}")
    return insights


def monthly_summary(df):
    if df.empty or "Transaction Date" not in df.columns:
        return pd.DataFrame()

    out = (
        df.groupby(["Year", "Month"], dropna=False)
        .agg(
            transactions=("Id", "count") if "Id" in df.columns else ("Transaction Date", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in df.columns else ("Transaction Date", "count"),
            risk_transactions=("risk_score", lambda x: (x > 0).sum()) if "risk_score" in df.columns else ("Transaction Date", "count"),
            canceled_transactions=("flag_canceled", "sum") if "flag_canceled" in df.columns else ("Transaction Date", "count")
        )
        .reset_index()
        .sort_values(["Year", "Month"])
    )

    out["period"] = out["Year"].astype("Int64").astype(str) + "-" + out["Month"].astype("Int64").astype(str).str.zfill(2)
    return out


@st.cache_data
def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")