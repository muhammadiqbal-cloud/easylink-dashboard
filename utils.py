def first_existing_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


@st.cache_data(ttl=300)
def customer_segments(df):
    if "Name" not in df.columns or df.empty:
        return pd.DataFrame()

    user_counts = (
        df.groupby("Name", dropna=False)
        .agg(
            transactions=("Id", "count") if "Id" in df.columns else ("Name", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in df.columns else ("Name", "count")
        )
        .reset_index()
    )

    def segment(x):
        if x == 1:
            return "New"
        elif x <= 3:
            return "Occasional"
        else:
            return "Loyal"

    user_counts["segment"] = user_counts["transactions"].apply(segment)
    return user_counts


@st.cache_data(ttl=300)
def repeat_vs_new_summary(df):
    seg = customer_segments(df)
    if seg.empty:
        return pd.DataFrame()

    out = (
        seg.groupby("segment", dropna=False)
        .agg(
            users=("Name", "count"),
            total_transactions=("transactions", "sum"),
            total_amount=("total_amount", "sum")
        )
        .reset_index()
    )
    return out


@st.cache_data(ttl=300)
def platform_monthly_growth(df):
    needed = {"Platform", "Year", "Month"}
    if not needed.issubset(df.columns) or df.empty:
        return pd.DataFrame()

    out = (
        df.groupby(["Platform", "Year", "Month"], dropna=False)
        .agg(
            transactions=("Id", "count") if "Id" in df.columns else ("Platform", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in df.columns else ("Platform", "count")
        )
        .reset_index()
        .sort_values(["Platform", "Year", "Month"])
    )

    out["period"] = out["Year"].astype("Int64").astype(str) + "-" + out["Month"].astype("Int64").astype(str).str.zfill(2)
    out["growth_pct"] = out.groupby("Platform")["transactions"].pct_change() * 100
    return out


@st.cache_data(ttl=300)
def country_monthly_growth(df):
    needed = {"Recipient Country", "Year", "Month"}
    if not needed.issubset(df.columns) or df.empty:
        return pd.DataFrame()

    out = (
        df.groupby(["Recipient Country", "Year", "Month"], dropna=False)
        .agg(
            transactions=("Id", "count") if "Id" in df.columns else ("Recipient Country", "count"),
            total_amount=("Amount Sent", "sum") if "Amount Sent" in df.columns else ("Recipient Country", "count")
        )
        .reset_index()
        .sort_values(["Recipient Country", "Year", "Month"])
    )

    out["period"] = out["Year"].astype("Int64").astype(str) + "-" + out["Month"].astype("Int64").astype(str).str.zfill(2)
    out["growth_pct"] = out.groupby("Recipient Country")["transactions"].pct_change() * 100
    return out


@st.cache_data(ttl=300)
def drop_detection(df, threshold=-30):
    ms = monthly_summary(df)
    if ms.empty:
        return pd.DataFrame()

    ms = ms.copy()
    ms["growth_pct"] = ms["transactions"].pct_change() * 100
    return ms[ms["growth_pct"] <= threshold].copy()


@st.cache_data(ttl=300)
def voucher_promo_summary(df):
    if df.empty:
        return {}

    voucher_col = first_existing_column(df, ["Voucher Code", "voucher_code", "Voucher", "Kode Voucher"])
    promo_col = first_existing_column(df, ["Promo Code", "promo_code", "Promo Name", "Promo", "Nama Promo"])
    discount_col = first_existing_column(df, ["Discount Amount", "discount_amount", "Discount", "Nominal Promo", "Promo Amount"])

    result = {
        "voucher_col": voucher_col,
        "promo_col": promo_col,
        "discount_col": discount_col,
        "voucher_usage": pd.DataFrame(),
        "promo_usage": pd.DataFrame(),
        "promo_vs_nonpromo": pd.DataFrame(),
    }

    temp = df.copy()

    if discount_col:
        temp[discount_col] = pd.to_numeric(temp[discount_col], errors="coerce").fillna(0)

    if voucher_col:
        temp[voucher_col] = temp[voucher_col].astype(str).str.strip()
        temp[voucher_col] = temp[voucher_col].replace({"nan": "", "None": "", "<NA>": ""})

        voucher_usage = (
            temp[temp[voucher_col] != ""]
            .groupby(voucher_col, dropna=False)
            .agg(
                transactions=("Id", "count") if "Id" in temp.columns else (voucher_col, "count"),
                total_amount=("Amount Sent", "sum") if "Amount Sent" in temp.columns else (voucher_col, "count"),
                avg_amount=("Amount Sent", "mean") if "Amount Sent" in temp.columns else (voucher_col, "count"),
            )
            .reset_index()
            .sort_values(["transactions", "total_amount"], ascending=[False, False])
        )

        if discount_col and not voucher_usage.empty:
            discount_map = (
                temp[temp[voucher_col] != ""]
                .groupby(voucher_col, dropna=False)[discount_col]
                .sum()
                .reset_index(name="total_discount")
            )
            voucher_usage = voucher_usage.merge(discount_map, on=voucher_col, how="left")

        result["voucher_usage"] = voucher_usage

    if promo_col:
        temp[promo_col] = temp[promo_col].astype(str).str.strip()
        temp[promo_col] = temp[promo_col].replace({"nan": "", "None": "", "<NA>": ""})

        promo_usage = (
            temp[temp[promo_col] != ""]
            .groupby(promo_col, dropna=False)
            .agg(
                transactions=("Id", "count") if "Id" in temp.columns else (promo_col, "count"),
                total_amount=("Amount Sent", "sum") if "Amount Sent" in temp.columns else (promo_col, "count"),
                avg_amount=("Amount Sent", "mean") if "Amount Sent" in temp.columns else (promo_col, "count"),
            )
            .reset_index()
            .sort_values(["transactions", "total_amount"], ascending=[False, False])
        )

        if discount_col and not promo_usage.empty:
            discount_map = (
                temp[temp[promo_col] != ""]
                .groupby(promo_col, dropna=False)[discount_col]
                .sum()
                .reset_index(name="total_discount")
            )
            promo_usage = promo_usage.merge(discount_map, on=promo_col, how="left")

        result["promo_usage"] = promo_usage

    if voucher_col or promo_col:
        has_promo = pd.Series(False, index=temp.index)

        if voucher_col:
            has_promo = has_promo | (temp[voucher_col] != "")
        if promo_col:
            has_promo = has_promo | (temp[promo_col] != "")

        temp["promo_flag"] = has_promo.map({True: "With Promo/Voucher", False: "No Promo/Voucher"})

        promo_vs_nonpromo = (
            temp.groupby("promo_flag", dropna=False)
            .agg(
                transactions=("Id", "count") if "Id" in temp.columns else ("promo_flag", "count"),
                total_amount=("Amount Sent", "sum") if "Amount Sent" in temp.columns else ("promo_flag", "count"),
                avg_amount=("Amount Sent", "mean") if "Amount Sent" in temp.columns else ("promo_flag", "count"),
            )
            .reset_index()
        )

        if discount_col:
            discount_sum = temp.groupby("promo_flag", dropna=False)[discount_col].sum().reset_index(name="total_discount")
            promo_vs_nonpromo = promo_vs_nonpromo.merge(discount_sum, on="promo_flag", how="left")

        result["promo_vs_nonpromo"] = promo_vs_nonpromo

    return result


def build_marketing_advanced_insights(df):
    insights = []

    if df.empty:
        return insights

    if "Platform" in df.columns:
        tg = top_group(df, "Platform")
        if not tg.empty:
            row = tg.iloc[0]
            insights.append(f"Platform paling kuat adalah {row['Platform']} dengan {format_number(row['transactions'])} transaksi.")

    if "Recipient Country" in df.columns:
        tg = top_group(df, "Recipient Country")
        if not tg.empty:
            row = tg.iloc[0]
            insights.append(f"Negara tujuan teratas adalah {row['Recipient Country']} dengan {format_number(row['transactions'])} transaksi.")

    if "Purpose" in df.columns:
        tg = top_group(df, "Purpose")
        if not tg.empty:
            row = tg.iloc[0]
            insights.append(f"Purpose paling dominan adalah {row['Purpose']}.")

    seg = repeat_vs_new_summary(df)
    if not seg.empty:
        total_users = seg["users"].sum()
        loyal_users = seg.loc[seg["segment"] == "Loyal", "users"].sum() if "Loyal" in seg["segment"].values else 0
        new_users = seg.loc[seg["segment"] == "New", "users"].sum() if "New" in seg["segment"].values else 0

        if total_users > 0:
            loyal_pct = loyal_users / total_users * 100
            new_pct = new_users / total_users * 100
            insights.append(f"Komposisi user baru sekitar {format_percent(new_pct)} dan user loyal sekitar {format_percent(loyal_pct)}.")

    drops = drop_detection(df, threshold=-30)
    if not drops.empty:
        latest_drop = drops.iloc[-1]
        insights.append(
            f"Terdapat penurunan signifikan pada {latest_drop['period']} sebesar {latest_drop['growth_pct']:.2f}% dibanding periode sebelumnya."
        )

    promo_data = voucher_promo_summary(df)
    promo_vs_nonpromo = promo_data.get("promo_vs_nonpromo", pd.DataFrame())
    if not promo_vs_nonpromo.empty and len(promo_vs_nonpromo) >= 2:
        insights.append("Promo/voucher sudah dapat dibandingkan terhadap transaksi non-promo untuk melihat kualitas volume dan nominal.")

    return insights