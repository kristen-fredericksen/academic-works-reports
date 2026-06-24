"""Academic Works reporting dashboard."""

import io

import pandas as pd
import streamlit as st

from data_loader import (
    COMBINED_SETS,
    CONTAINER_SETS,
    harvest_timestamp,
    load_backup_identifiers,
    load_records,
)

st.set_page_config(
    page_title="Academic Works reports",
    page_icon=":books:",
    layout="wide",
)

# --- Sidebar -----------------------------------------------------------------

with st.sidebar:
    st.title("Academic Works reports")
    st.caption(f"Data refreshed {harvest_timestamp()}")
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

df = load_records()
total_records = len(df)

st.sidebar.markdown(f"**{total_records:,}** records loaded")


def excel_download(dataframe: pd.DataFrame, filename: str, label: str = "Download as Excel"):
    """Provide a download button for a DataFrame as Excel."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Records")
    st.download_button(
        label=label,
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Tabs --------------------------------------------------------------------

tab_overview, tab_health, tab_by_school, tab_search, tab_changes = st.tabs([
    "Overview",
    "Health check",
    "By school",
    "Find a record",
    "What's new",
])

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

with tab_overview:
    st.subheader("Snapshot of everything in Academic Works")

    counts = {label: int(df[f"in_{label}"].sum()) for label in COMBINED_SETS}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Theses", f"{counts['etds']:,}")
    col2.metric("Publications", f"{counts['pubs']:,}")
    col3.metric("OERs", f"{counts['oers']:,}")
    col4.metric("Archives", f"{counts['arch']:,}")

    st.markdown("#### Records added per year")
    year_df = df[df["year"].str.match(r"^\d{4}$", na=False)].copy()
    year_df["year"] = year_df["year"].astype(int)
    year_df = year_df[year_df["year"] >= 2010]
    year_counts = year_df.groupby("year").size().reset_index(name="records")
    st.bar_chart(year_counts, x="year", y="records", height=300)

    st.caption(f"Showing {len(year_df):,} records with a parsable year (out of {total_records:,} total)")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

with tab_health:
    st.subheader("Collections not rolling up into a combined set")
    st.caption("Records in series-level collections that don't appear in publication:etds, :pubs, :oers, or :arch.")

    orphan_mask = (
        ~df["in_etds"] & ~df["in_pubs"] & ~df["in_oers"] & ~df["in_arch"]
        & ~df["series"].isin(CONTAINER_SETS)
    )
    orphans = df[orphan_mask].copy()

    summary = (
        orphans.groupby(["series", "school"])
        .size()
        .reset_index(name="orphaned_records")
        .sort_values("orphaned_records", ascending=False)
    )

    st.warning(
        f"**{len(orphans):,} records** across **{summary['series'].nunique()} collections** "
        "aren't in any combined set."
    )

    st.dataframe(summary, use_container_width=True, hide_index=True)
    excel_download(orphans, "orphaned_records.xlsx", "Download all orphan records as Excel")

# ---------------------------------------------------------------------------
# By school
# ---------------------------------------------------------------------------

with tab_by_school:
    st.subheader("Records by school and category")

    school_options = sorted(df["school"].unique().tolist())
    year_options = sorted(
        df[df["year"].str.match(r"^\d{4}$", na=False)]["year"].unique().tolist(),
        reverse=True,
    )

    col1, col2 = st.columns(2)
    selected_schools = col1.multiselect("Schools", school_options, default=[])
    selected_years = col2.multiselect("Years", year_options, default=[])

    filtered = df.copy()
    if selected_schools:
        filtered = filtered[filtered["school"].isin(selected_schools)]
    if selected_years:
        filtered = filtered[filtered["year"].isin(selected_years)]

    school_table = (
        filtered.groupby("school")
        .agg(
            theses=("in_etds", "sum"),
            pubs=("in_pubs", "sum"),
            oers=("in_oers", "sum"),
            archives=("in_arch", "sum"),
            total=("identifier", "count"),
        )
        .sort_values("total", ascending=False)
        .reset_index()
    )

    totals_row = pd.DataFrame([{
        "school": "All schools",
        "theses": int(school_table["theses"].sum()),
        "pubs": int(school_table["pubs"].sum()),
        "oers": int(school_table["oers"].sum()),
        "archives": int(school_table["archives"].sum()),
        "total": int(school_table["total"].sum()),
    }])
    display_table = pd.concat([school_table, totals_row], ignore_index=True)

    st.dataframe(display_table, use_container_width=True, hide_index=True)
    excel_download(display_table, "records_by_school.xlsx")

# ---------------------------------------------------------------------------
# Find a record
# ---------------------------------------------------------------------------

with tab_search:
    st.subheader("Find a record")
    st.caption("Search by any combination of manuscript ID, series, author, or title.")

    series_options = ["All series"] + sorted(
        df[~df["series"].isin(CONTAINER_SETS)]["series"].unique().tolist()
    )

    row1_col1, row1_col2 = st.columns(2)
    manuscript_id_query = row1_col1.text_input("Manuscript ID", placeholder="e.g. 1022")
    series_query = row1_col2.selectbox("Series", series_options)

    row2_col1, row2_col2 = st.columns(2)
    author_query = row2_col1.text_input("Author", placeholder="Last name or full name")
    title_query = row2_col2.text_input("Title", placeholder="Word or phrase")

    results = df.copy()
    if manuscript_id_query.strip():
        results = results[results["manuscript_id"].str.contains(manuscript_id_query.strip(), na=False)]
    if series_query != "All series":
        results = results[results["series"] == series_query]
    if author_query.strip():
        results = results[results["authors"].str.contains(author_query.strip(), case=False, na=False)]
    if title_query.strip():
        results = results[results["title"].str.contains(title_query.strip(), case=False, na=False)]

    any_filter = any([
        manuscript_id_query.strip(),
        series_query != "All series",
        author_query.strip(),
        title_query.strip(),
    ])

    if not any_filter:
        st.info("Enter a search term in any field above to find records.")
    else:
        st.caption(f"{len(results):,} results")
        display = results[["manuscript_id", "series", "title", "authors", "year", "school"]].copy()
        display.columns = ["Manuscript ID", "Series", "Title", "Author(s)", "Year", "School"]
        st.dataframe(display.head(500), use_container_width=True, hide_index=True)
        if len(results) > 500:
            st.caption(f"Showing first 500 of {len(results):,} results. Download for the full list.")
        excel_download(results, "search_results.xlsx")

# ---------------------------------------------------------------------------
# What's new
# ---------------------------------------------------------------------------

with tab_changes:
    st.subheader("What's changed since the last harvest")

    backup_ids = load_backup_identifiers()
    if not backup_ids:
        st.info("No backup harvest found at `data/oai_dc_20260405/` for comparison.")
    else:
        current_ids = set(df["identifier"])
        new_ids = current_ids - backup_ids
        removed_ids = backup_ids - current_ids

        col1, col2, col3 = st.columns(3)
        col1.metric("New records", f"+{len(new_ids):,}")
        col2.metric("Removed records", f"-{len(removed_ids):,}")
        col3.metric("Total now", f"{len(current_ids):,}")

        new_df = df[df["identifier"].isin(new_ids)].copy()

        st.markdown("#### New records by school")
        by_school = (
            new_df.groupby("school")
            .size()
            .reset_index(name="new_records")
            .sort_values("new_records", ascending=False)
        )
        st.dataframe(by_school, use_container_width=True, hide_index=True)

        st.markdown("#### New record titles")
        display_new = new_df[["manuscript_id", "series", "title", "authors", "year", "school"]].copy()
        display_new.columns = ["Manuscript ID", "Series", "Title", "Author(s)", "Year", "School"]
        st.dataframe(display_new.head(500), use_container_width=True, hide_index=True)
        excel_download(new_df, "new_records.xlsx")
