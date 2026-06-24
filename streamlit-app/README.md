# Academic Works reports

A Streamlit dashboard for browsing CUNY Academic Works metadata harvested via
OAI-PMH. Built for the Academic Works administrator to spot orphaned records,
break records down by school, search across the whole repository, and see
what's changed between harvests.

## Tabs

- **Overview** — Headline counts (theses, publications, OERs, archives) and a
  bar chart of records added per year.
- **Health check** — Records that exist in series-level sets but aren't in any
  of the four combined sets (`publication:etds`, `:pubs`, `:oers`, `:arch`).
- **By school** — Grouped table with optional school and year filters.
- **Find a record** — Search by manuscript ID, series, author, or title.
- **What's new** — Diff between the current harvest and a prior backup.

Every tab has an Excel download button.

## Local development

```bash
cd academic-works-harvest
python3 -m venv venv && source venv/bin/activate
pip install -r streamlit-app/requirements.txt

# First time only — also need the harvester deps
pip install -r requirements.txt

# Harvest fresh data (slow, several hours)
python3 src/harvest.py

# Bundle the XML into a small Parquet file the app loads from
python3 streamlit-app/build_data.py

# Start the app
streamlit run streamlit-app/app.py
```

## Deploying to Streamlit Community Cloud

1. Push this repo to GitHub. The `.gitignore` excludes the raw XML harvest;
   only the small Parquet bundle in `streamlit-app/data/` is committed.
2. Sign in at [share.streamlit.io](https://share.streamlit.io).
3. Create a new app, point it at this repo, and set:
   - **Main file path**: `streamlit-app/app.py`
   - **Branch**: `main`
4. Streamlit Cloud installs from `streamlit-app/requirements.txt`
   automatically.

To refresh the deployed data, re-run `python3 streamlit-app/build_data.py`
locally, commit the updated `streamlit-app/data/records.parquet`, and push.
The deployed app picks up the new file on the next reboot.
