import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="AutoInsight | Data Workspace", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1.5rem;max-width:1450px}
[data-testid="stSidebar"]{border-right:1px solid rgba(128,128,128,.2)}
.hero{padding:1.4rem 1.6rem;border-radius:18px;margin-bottom:1rem;background:linear-gradient(120deg,#12243a,#1b4965,#2c6e75);color:white}
.hero h1{color:white;margin:0 0 .35rem 0}.hero p{color:#e4eef4;margin:0}
div[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.2);padding:.8rem 1rem;border-radius:12px}
</style>
<div class="hero"><h1>AutoInsight Impact Engine</h1>
<p>Turn raw datasets into explainable insights with a guided, reversible workflow.</p></div>
""", unsafe_allow_html=True)

STEPS = ["1 · Upload", "2 · Overview", "3 · Explore", "4 · Clean", "5 · Review impact", "6 · Export"]
for key, default in [("step", STEPS[0]), ("source_df", None), ("working_df", None),
                     ("source_name", ""), ("change_log", []), ("undo_stack", [])]:
    if key not in st.session_state:
        st.session_state[key] = default

def move(step):
    st.session_state.step = step

def potential_outlier_count(series):
    """Count numeric values outside 1.5×IQR fences; these are flags, not errors."""
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 4:
        return 0
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = q3 - q1
    if pd.isna(iqr) or iqr == 0:
        return 0
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((values < lower) | (values > upper)).sum())

def profile(df):
    numeric_columns = set(df.select_dtypes(include="number").columns)
    return pd.DataFrame({
        "Column": [str(c) for c in df.columns],
        "Data type": [str(x) for x in df.dtypes],
        "Missing": df.isna().sum().values,
        "Missing %": (df.isna().sum().values / max(len(df), 1) * 100).round(2),
        "Unique values": df.nunique(dropna=True).values,
        "Potential outliers": [potential_outlier_count(df[c]) if c in numeric_columns else "—" for c in df.columns],
    })

def quality_findings(df):
    """Return explainable, actionable data-quality observations for the current dataset."""
    findings = []
    total_cells = max(len(df) * len(df.columns), 1)
    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    if missing_cells:
        rate = missing_cells / total_cells * 100
        findings.append({"Finding": "Missing values", "Affected": f"{missing_cells:,} cells ({rate:.1f}%)",
                         "Suggested action": "Review missingness by column; fill or remove values only when appropriate."})
    if duplicate_rows:
        findings.append({"Finding": "Exact duplicate rows", "Affected": f"{duplicate_rows:,} rows",
                         "Suggested action": "Review duplicates before removing them; repeated rows may sometimes be valid."})
    for col in df.select_dtypes(include="number").columns:
        count = potential_outlier_count(df[col])
        if count:
            findings.append({"Finding": f"Potential outliers · {col}", "Affected": f"{count:,} values",
                             "Suggested action": "Inspect the values and domain context; do not automatically delete outliers."})
    if not findings:
        findings.append({"Finding": "No common issues detected", "Affected": "—",
                         "Suggested action": "Check business rules and expected ranges; basic checks cannot prove data is correct."})
    return pd.DataFrame(findings)

def quality(df):
    if df.empty or not len(df.columns):
        return 0
    total = max(len(df) * len(df.columns), 1)
    missing_rate = df.isna().sum().sum() / total
    duplicate_rate = df.duplicated().sum() / max(len(df), 1)
    return max(0, min(100, round(100 * (1 - min(1, .7 * missing_rate + .3 * duplicate_rate)))))

def reset_data(df, name):
    st.session_state.source_df = df.copy(deep=True)
    st.session_state.working_df = df.copy(deep=True)
    st.session_state.source_name = name
    st.session_state.change_log = []
    st.session_state.undo_stack = []
    st.session_state.step = STEPS[1]

with st.sidebar:
    st.markdown("## 📊 AutoInsight")
    st.caption("DATA QUALITY · EXPLORATION · CLEANING")
    st.divider()
    st.markdown("### Workflow")
    for step in STEPS:
        if st.button(("● " if st.session_state.step == step else "○ ") + step,
                     key="nav_" + step, use_container_width=True,
                     disabled=(step != STEPS[0] and st.session_state.source_df is None),
                     type="primary" if st.session_state.step == step else "secondary"):
            move(step)
            st.rerun()
    if st.session_state.source_df is not None:
        st.divider()
        st.caption("ACTIVE DATASET")
        st.write("**" + st.session_state.source_name + "**")
        st.caption(f"{len(st.session_state.working_df):,} rows · {len(st.session_state.working_df.columns):,} columns")
        if st.button("Reset to original", use_container_width=True):
            st.session_state.working_df = st.session_state.source_df.copy(deep=True)
            st.session_state.change_log = []
            st.session_state.undo_stack = []
            st.rerun()

idx = STEPS.index(st.session_state.step)
st.progress((idx + 1) / len(STEPS), text=f"Step {idx + 1} of {len(STEPS)} · {STEPS[idx].split('·', 1)[1].strip()}")

if st.session_state.step == STEPS[0]:
    st.subheader("Start with your data")
    st.write("Upload a CSV file to begin, or load the sample file from your project folder.")
    col1, col2 = st.columns([1.2, 1])
    with col1:
        uploaded = st.file_uploader("Choose a CSV file", type=["csv"])
        if uploaded:
            st.caption(f"Selected: {uploaded.name} · {uploaded.size:,} bytes")
            if st.button("Load dataset", type="primary", use_container_width=True):
                try:
                    uploaded.seek(0)
                    data = pd.read_csv(uploaded, low_memory=False)
                    if data.empty:
                        st.error("The CSV has no data rows.")
                    else:
                        reset_data(data, uploaded.name)
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not read the CSV: {e}")
    with col2:
        st.markdown("#### Or use the sample")
        st.write("Test the workflow using `sample_data.csv` in the project root.")
        if st.button("Load sample_data.csv", use_container_width=True):
            try:
                data = pd.read_csv("sample_data.csv", low_memory=False)
                if data.empty:
                    st.error("sample_data.csv has no data rows.")
                else:
                    reset_data(data, "sample_data.csv")
                    st.rerun()
            except FileNotFoundError:
                st.warning("sample_data.csv was not found in the current working directory. Upload a CSV instead.")
            except Exception as e:
                st.error(f"Could not read sample_data.csv: {e}")
    st.divider()
    a, b, c = st.columns(3)
    a.info("**01 · Profile**\n\nUnderstand data quality and column types.")
    b.info("**02 · Explore**\n\nView distributions and numeric relationships.")
    c.info("**03 · Clean & export**\n\nReview changes before downloading results.")

else:
    if st.session_state.source_df is None:
        st.warning("Load a dataset first.")
        if st.button("Go to Upload", type="primary"):
            move(STEPS[0]); st.rerun()
        st.stop()

    df = st.session_state.working_df
    original = st.session_state.source_df
    numeric = df.select_dtypes(include="number").columns.tolist()
    categorical = df.select_dtypes(include=["object", "category", "bool", "string"]).columns.tolist()

    if st.session_state.step == STEPS[1]:
        st.subheader("Dataset overview")
        st.caption("A quick health check of the current working dataset.")
        m = st.columns(4)
        m[0].metric("Rows", f"{len(df):,}")
        m[1].metric("Columns", f"{len(df.columns):,}")
        m[2].metric("Missing cells", f"{int(df.isna().sum().sum()):,}")
        m[3].metric("Exact duplicate rows", f"{int(df.duplicated().sum()):,}")
        x, y = st.columns([1, 2])
        with x:
            st.metric("Data health score", f"{quality(df)}/100")
            st.progress(quality(df) / 100)
            st.caption("Heuristic only; not a certification of correctness.")
        with y:
            st.markdown("#### Dataset preview")
            st.dataframe(df.head(100), width="stretch", height=300)
        st.markdown("#### Column profile")
        st.dataframe(profile(df), width="stretch", hide_index=True)
        st.markdown("#### Data quality findings")
        st.caption("Outliers are statistical flags for review, not automatically incorrect values. The health score does not penalize outliers.")
        st.dataframe(quality_findings(df), width="stretch", hide_index=True)
        
        st.divider()
        st.subheader("💬 Ask Questions About Your Dataset")
        st.caption(
            "Ask questions about rows, columns, missing values, "
            "duplicates, and numeric statistics."
        )

        question = st.text_input(
            "Your question",
            placeholder="e.g. How many rows are in this dataset?",
            key="dataset_question"
        )

        if st.button("Get Answer", type="primary", key="answer_question_btn"):
            if not question.strip():
                st.warning("Please enter a question.")
            else:
                q = question.strip().lower()

                if "row" in q:
                    st.success(f"Your dataset contains {len(df):,} rows.")

                elif "column" in q:
                    st.success(
                        f"Your dataset contains {len(df.columns):,} columns."
                    )

                elif "missing" in q or "null" in q or "na values" in q:
                    missing = int(df.isna().sum().sum())
                    st.success(f"Your dataset contains {missing:,} missing cells.")
                    st.dataframe(
                        df.isna().sum().rename("Missing values").to_frame(),
                        use_container_width=True
                    )

                elif "duplicate" in q:
                    duplicates = int(df.duplicated().sum())
                    st.success(f"Your dataset contains {duplicates:,} duplicate rows.")

                elif "average" in q or "mean" in q:
                    if numeric:
                        selected_col = st.selectbox(
                            "Choose the column",
                            numeric,
                            key="qa_mean_column"
                        )
                        st.info(
                            f"Mean of {selected_col}: "
                            f"{df[selected_col].mean():,.4f}"
                        )
                    else:
                        st.warning("This dataset has no numeric columns.")

                elif "median" in q:
                    if numeric:
                        selected_col = st.selectbox(
                            "Choose the column",
                            numeric,
                            key="qa_median_column"
                        )
                        st.info(
                            f"Median of {selected_col}: "
                            f"{df[selected_col].median():,.4f}"
                        )
                    else:
                        st.warning("This dataset has no numeric columns.")

                else:
                    st.warning(
                        "I can't answer that question yet. Try asking about "
                        "rows, columns, missing values, duplicates, mean, or median."
                    )

        if st.button("Next: Explore charts →", type="primary"):
            move(STEPS[2])
            st.rerun()

        if st.button("Next: Explore charts →", type="primary",key="next_explore_charts_btn"):
            move(STEPS[2])
            st.rerun()

    elif st.session_state.step == STEPS[2]:
        st.subheader("Automatic EDA: graphs, relationships and maps")
        st.caption("Charts are selected from the column types detected in your uploaded dataset. Not every dataset supports every chart.")
        chart_limit = st.selectbox("Maximum rows used for charts", [2000, 10000, 25000, 50000], index=1)
        chart_df = df.head(chart_limit).copy() if len(df) > chart_limit else df.copy()

        # Identify date-like columns without changing the user's underlying data.
        date_cols = []
        for col in chart_df.columns:
            if pd.api.types.is_datetime64_any_dtype(chart_df[col]):
                date_cols.append(col)
            elif chart_df[col].dtype == "object" or pd.api.types.is_string_dtype(chart_df[col]):
                sample = chart_df[col].dropna().astype(str).head(300)
                if len(sample) and any(token in str(col).lower() for token in ["date", "time", "year", "month"]):
                    parsed = pd.to_datetime(sample, errors="coerce")
                    if parsed.notna().mean() >= 0.7:
                        date_cols.append(col)

        lower_names = {str(c).strip().lower(): c for c in chart_df.columns}
        lat_col = next((c for c in chart_df.columns if str(c).strip().lower() in {"lat", "latitude", "geo_lat", "y_coord"}), None)
        lon_col = next((c for c in chart_df.columns if str(c).strip().lower() in {"lon", "lng", "long", "longitude", "geo_lon", "x_coord"}), None)
        country_col = next((c for c in chart_df.columns if str(c).strip().lower() in {"country", "country_name", "nation"}), None)

        tabs = st.tabs(["Overview charts", "Relationships", "Time trends", "Maps"])
        with tabs[0]:
            if numeric:
                st.markdown("#### Numeric distributions")
                ncol = st.selectbox("Choose a numeric column", numeric, key="auto_hist_col")
                fig = px.histogram(chart_df, x=ncol, marginal="box", nbins=40, title=f"Distribution of {ncol}", template="plotly_white")
                fig.update_layout(height=420)
                st.plotly_chart(fig, use_container_width=True)
                fig = px.box(chart_df, y=ncol, points="outliers", title=f"Box plot · {ncol}", template="plotly_white")
                fig.update_layout(height=380)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No numeric columns detected. Numeric distribution charts need numeric data.")
            if categorical:
                st.markdown("#### Category frequency")
                ccol = st.selectbox("Choose a categorical column", categorical, key="auto_bar_col")
                counts = chart_df[ccol].astype("string").fillna("(Missing)").value_counts().head(25).rename_axis("Category").reset_index(name="Count")
                fig = px.bar(counts, x="Category", y="Count", title=f"Top categories · {ccol}", template="plotly_white")
                fig.update_layout(height=420, xaxis_tickangle=-35)
                st.plotly_chart(fig, use_container_width=True)
                pie_counts = counts.head(10)
                fig = px.pie(pie_counts, names="Category", values="Count", title=f"Category share · {ccol} (top 10)", hole=.35)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No categorical columns detected for category charts.")

        with tabs[1]:
            if len(numeric) >= 2:
                selected = st.multiselect("Columns for correlation analysis", numeric, default=numeric[:min(12, len(numeric))], max_selections=20)
                if len(selected) >= 2:
                    corr = chart_df[selected].corr(numeric_only=True)
                    fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto", title="Correlation heatmap", template="plotly_white")
                    fig.update_layout(height=max(420, 35 * len(selected)))
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("Correlation measures association; it does not prove causation.")
                    pairs = chart_df[selected].dropna()
                    if len(pairs) > 3000:
                        pairs = pairs.sample(3000, random_state=42)
                    if len(selected) >= 2:
                        fig = px.scatter_matrix(pairs, dimensions=selected[:6], title="Scatter-matrix relationships (up to 6 columns)", template="plotly_white")
                        fig.update_layout(height=750)
                        st.plotly_chart(fig, use_container_width=True)
                    xcol, ycol = st.columns(2)
                    with xcol:
                        x_axis = st.selectbox("Scatter X-axis", numeric, key="auto_scatter_x")
                    with ycol:
                        y_axis = st.selectbox("Scatter Y-axis", [c for c in numeric if c != x_axis] or numeric, key="auto_scatter_y")
                    points = chart_df[[x_axis, y_axis]].dropna()
                    if len(points) > 10000:
                        points = points.sample(10000, random_state=42)
                    fig = px.scatter(points, x=x_axis, y=y_axis, opacity=.65, title=f"{x_axis} vs {y_axis}", trendline="ols" if len(points) >= 3 else None, template="plotly_white")
                    fig.update_layout(height=430)
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("At least two numeric columns are needed for correlation and scatter relationships.")
            if len(numeric) and categorical:
                st.markdown("#### Numeric values by category")
                cat_group = st.selectbox("Group by", categorical, key="auto_group_cat")
                num_group = st.selectbox("Measure", numeric, key="auto_group_num")
                agg = chart_df.groupby(cat_group, dropna=False)[num_group].mean().sort_values(ascending=False).head(25).reset_index()
                fig = px.bar(agg, x=cat_group, y=num_group, title=f"Average {num_group} by {cat_group}", template="plotly_white")
                fig.update_layout(height=420, xaxis_tickangle=-35)
                st.plotly_chart(fig, use_container_width=True)

        with tabs[2]:
            if date_cols and numeric:
                date_col = st.selectbox("Date/time column", date_cols, key="auto_time_date")
                value_col = st.selectbox("Numeric measure", numeric, key="auto_time_num")
                trend = chart_df[[date_col, value_col]].copy()
                trend[date_col] = pd.to_datetime(trend[date_col], errors="coerce")
                trend = trend.dropna().sort_values(date_col)
                if not trend.empty:
                    fig = px.line(trend, x=date_col, y=value_col, title=f"{value_col} over time", markers=True, template="plotly_white")
                    fig.update_layout(height=430)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("The detected date column has no valid date/measure pairs.")
            else:
                st.info("Time trends are available when a date/time column and a numeric measure are detected. Name date columns clearly (for example, order_date).")

        with tabs[3]:
            if lat_col and lon_col:
                map_df = chart_df.copy()
                map_df[lat_col] = pd.to_numeric(map_df[lat_col], errors="coerce")
                map_df[lon_col] = pd.to_numeric(map_df[lon_col], errors="coerce")
                map_df = map_df.dropna(subset=[lat_col, lon_col])
                map_df = map_df[map_df[lat_col].between(-90, 90) & map_df[lon_col].between(-180, 180)]
                if not map_df.empty:
                    color_col = st.selectbox("Optional map color", ["(none)"] + numeric, key="auto_map_color")
                    fig = px.scatter_map(map_df, lat=lat_col, lon=lon_col,
                                         color=None if color_col == "(none)" else color_col,
                                         hover_name=country_col if country_col else None,
                                         zoom=1, height=560, title="Geographic points", map_style="open-street-map")
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption(f"Mapped {len(map_df):,} valid coordinate rows. Map tiles require an internet connection in the browser.")
                else:
                    st.warning("Latitude/longitude columns were found, but no rows have valid coordinate values.")
            else:
                st.info("No latitude/longitude columns detected. Geographic maps need coordinates or place names that can be geocoded. This app does not geocode city names automatically, to avoid unreliable locations and external data sharing.")
            if country_col and numeric:
                st.markdown("#### Country-level choropleth")
                measure = st.selectbox("Value to aggregate by country", numeric, key="auto_country_measure")
                geo = chart_df[[country_col, measure]].dropna().copy()
                if not geo.empty:
                    geo = geo.groupby(country_col, as_index=False)[measure].mean()
                    try:
                        fig = px.choropleth(geo, locations=country_col, locationmode="country names", color=measure,
                                            title=f"Average {measure} by country", color_continuous_scale="Blues")
                        fig.update_layout(height=560)
                        st.plotly_chart(fig, use_container_width=True)
                        st.caption("Country names must be recognized by Plotly. For best results use standard English country names or ISO-3 codes with a matching location mode.")
                    except Exception as exc:
                        st.warning(f"Could not build the country map from this column: {exc}")

        st.caption(f"Charts use up to {len(chart_df):,} rows for responsiveness. Visualizations are generated only when compatible columns are detected.")
        if st.button("Next: Clean data →", type="primary"):
            move(STEPS[3]); st.rerun()

    elif st.session_state.step == STEPS[3]:
        st.subheader("Clean data")
        st.warning("Changes apply to a working copy. The original uploaded data is retained.")
        st.markdown("#### One-click conservative cleaning")
        st.caption("Removes fully empty rows/columns, trims leading/trailing whitespace in text cells, and removes exact duplicate rows. It does not guess missing values or delete statistical outliers.")
        if st.button("Run conservative auto-clean", type="primary", key="conservative_auto_clean"):
            before = df.copy(deep=True)
            cleaned = df.copy(deep=True)
            actions = []
            old_rows, old_cols = len(cleaned), len(cleaned.columns)
            cleaned = cleaned.dropna(axis=0, how="all")
            if len(cleaned) != old_rows:
                actions.append(f"Removed {old_rows-len(cleaned):,} fully empty rows")
            empty_cols = [c for c in cleaned.columns if cleaned[c].isna().all()]
            if empty_cols:
                cleaned = cleaned.drop(columns=empty_cols)
                actions.append(f"Removed {len(empty_cols):,} fully empty columns")
            trimmed_cols = 0
            for col in cleaned.select_dtypes(include=["object", "string"]).columns:
                updated = cleaned[col].map(lambda v: v.strip() if isinstance(v, str) else v)
                if not updated.equals(cleaned[col]):
                    cleaned[col] = updated
                    trimmed_cols += 1
            if trimmed_cols:
                actions.append(f"Trimmed whitespace in {trimmed_cols:,} text columns")
            pre_dedupe = len(cleaned)
            cleaned = cleaned.drop_duplicates().copy()
            if len(cleaned) != pre_dedupe:
                actions.append(f"Removed {pre_dedupe-len(cleaned):,} exact duplicate rows")
            if not actions:
                actions.append("No conservative cleaning changes were needed")
            st.session_state.undo_stack.append(df.copy(deep=True))
            st.session_state.working_df = cleaned
            st.session_state.change_log.append({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "actions": "; ".join(actions),
                "rows_before": len(before), "rows_after": len(cleaned),
                "rows_removed": len(before)-len(cleaned),
            })
            st.success("Auto-clean completed on the working copy. Review the impact before exporting.")
            st.rerun()
        with st.form("clean_form"):
            dedupe = st.checkbox(f"Remove exact duplicate rows ({int(df.duplicated().sum()):,} detected)")
            strategy = st.selectbox("Missing-value strategy", [
                "Do not change missing values",
                "Fill numeric columns with median; text columns with mode",
                "Fill numeric columns with mean; text columns with mode",
                "Drop rows containing any missing value",
            ])
            apply = st.form_submit_button("Apply selected cleaning", type="primary")
        if apply:
            before = df.copy(deep=True)
            cleaned = df.copy(deep=True)
            actions = []
            if dedupe:
                old = len(cleaned)
                cleaned = cleaned.drop_duplicates().copy()
                actions.append(f"Removed {old-len(cleaned):,} exact duplicate rows")
            if strategy.startswith("Fill numeric columns with median") or strategy.startswith("Fill numeric columns with mean"):
                use_median = strategy.startswith("Fill numeric columns with median")
                filled = 0
                for col in cleaned.columns:
                    if cleaned[col].isna().any():
                        if pd.api.types.is_numeric_dtype(cleaned[col]):
                            val = cleaned[col].median() if use_median else cleaned[col].mean()
                            if pd.notna(val):
                                cleaned[col] = cleaned[col].fillna(val); filled += 1
                        else:
                            modes = cleaned[col].mode(dropna=True)
                            if not modes.empty:
                                cleaned[col] = cleaned[col].fillna(modes.iloc[0]); filled += 1
                actions.append(f"{'Median' if use_median else 'Mean'}/mode fill applied where possible in {filled} columns")
            elif strategy == "Drop rows containing any missing value":
                old = len(cleaned); cleaned = cleaned.dropna().copy()
                actions.append(f"Dropped {old-len(cleaned):,} rows containing missing values")
            if not actions:
                actions.append("No cleaning change selected")
            st.session_state.undo_stack.append(df.copy(deep=True))
            st.session_state.working_df = cleaned
            st.session_state.change_log.append({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "actions": "; ".join(actions),
                "rows_before": len(before), "rows_after": len(cleaned),
                "rows_removed": len(before)-len(cleaned),
            })
            st.success("Working copy updated.")
            st.rerun()
        st.markdown("#### Current working copy")
        m = st.columns(3)
        m[0].metric("Rows", f"{len(df):,}")
        m[1].metric("Missing cells", f"{int(df.isna().sum().sum()):,}")
        m[2].metric("Duplicate rows", f"{int(df.duplicated().sum()):,}")
        st.dataframe(df.head(100), width="stretch", height=280)
        if st.session_state.change_log:
            st.markdown("#### Change log")
            st.dataframe(pd.DataFrame(st.session_state.change_log), width="stretch", hide_index=True)
        if st.button("Undo last cleaning action", disabled=not st.session_state.undo_stack):
            st.session_state.working_df = st.session_state.undo_stack.pop()
            if st.session_state.change_log:
                st.session_state.change_log.pop()
            st.rerun()
        if st.button("Next: Review impact →", type="primary"):
            move(STEPS[4]); st.rerun()

    elif st.session_state.step == STEPS[4]:
        st.subheader("Review cleaning impact")
        cleaned = st.session_state.working_df
        before_rows, after_rows = len(original), len(cleaned)
        before_missing, after_missing = int(original.isna().sum().sum()), int(cleaned.isna().sum().sum())
        before_dupes, after_dupes = int(original.duplicated().sum()), int(cleaned.duplicated().sum())
        m = st.columns(4)
        m[0].metric("Rows before", f"{before_rows:,}")
        m[1].metric("Rows now", f"{after_rows:,}", delta=f"{after_rows-before_rows:+,}")
        m[2].metric("Missing before", f"{before_missing:,}")
        m[3].metric("Missing now", f"{after_missing:,}", delta=f"{after_missing-before_missing:+,}")
        comparison = pd.DataFrame([
            {"Metric": "Rows", "Original": before_rows, "Current": after_rows, "Change": after_rows-before_rows},
            {"Metric": "Missing cells", "Original": before_missing, "Current": after_missing, "Change": after_missing-before_missing},
            {"Metric": "Duplicate rows", "Original": before_dupes, "Current": after_dupes, "Change": after_dupes-before_dupes},
            {"Metric": "Columns", "Original": len(original.columns), "Current": len(cleaned.columns), "Change": len(cleaned.columns)-len(original.columns)},
        ])
        st.dataframe(comparison, width="stretch", hide_index=True)
        if st.session_state.change_log:
            st.dataframe(pd.DataFrame(st.session_state.change_log), width="stretch", hide_index=True)
        else:
            st.info("No cleaning operations have been recorded. You can still export the unchanged dataset.")
        st.caption("These are deterministic before-and-after counts, not a guarantee that the data is correct.")
        if st.button("Next: Export →", type="primary"):
            move(STEPS[5]); st.rerun()

    elif st.session_state.step == STEPS[5]:
        st.subheader("Export results")
        cleaned = st.session_state.working_df
        st.write("Download the current working copy, action log, and quality summary.")
        st.download_button("⬇ Download dataset (CSV)", cleaned.to_csv(index=False).encode("utf-8-sig"),
                           file_name="autoinsight_cleaned_data.csv", mime="text/csv", type="primary", use_container_width=True)
        log_json = json.dumps(st.session_state.change_log, indent=2, ensure_ascii=False)
        st.download_button("⬇ Download change log (JSON)", log_json.encode("utf-8"),
                           file_name="autoinsight_change_log.json", mime="application/json", use_container_width=True)
        summary = {
            "dataset": st.session_state.source_name,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "original_rows": len(original), "exported_rows": len(cleaned),
            "columns": len(cleaned.columns), "missing_cells": int(cleaned.isna().sum().sum()),
            "exact_duplicate_rows": int(cleaned.duplicated().sum()),
            "heuristic_data_health_score": quality(cleaned),
            "actions": st.session_state.change_log,
        }
        st.download_button("⬇ Download quality summary (JSON)", json.dumps(summary, indent=2).encode("utf-8"),
                           file_name="autoinsight_quality_summary.json", mime="application/json", use_container_width=True)
        m = st.columns(4)
        m[0].metric("Rows", f"{len(cleaned):,}")
        m[1].metric("Columns", f"{len(cleaned.columns):,}")
        m[2].metric("Missing cells", f"{int(cleaned.isna().sum().sum()):,}")
        m[3].metric("Health score", f"{quality(cleaned)}/100")
        if st.button("Start a new analysis", type="primary"):
            for key, value in [("source_df", None), ("working_df", None), ("source_name", ""),
                               ("change_log", []), ("undo_stack", []), ("step", STEPS[0])]:
                st.session_state[key] = value
            st.rerun()

# Consistent previous/next controls
if st.session_state.source_df is not None and st.session_state.step != STEPS[0]:
    st.divider()
    i = STEPS.index(st.session_state.step)
    c1, c2 = st.columns(2)
    if i > 1:
        if c1.button("← Previous step", use_container_width=True, key="footer_previous"):
            move(STEPS[i-1]); st.rerun()
    if i < len(STEPS)-1:
        if c2.button("Continue →", use_container_width=True, key="footer_continue"):
            move(STEPS[i+1]); st.rerun()
