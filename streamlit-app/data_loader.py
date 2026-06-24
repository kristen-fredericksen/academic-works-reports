"""Load harvested OAI-PMH XML into a single pandas DataFrame for the app."""

import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import pandas as pd
import streamlit as st

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
DC_NS = "http://purl.org/dc/elements/1.1/"

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data", "oai_dc")
BACKUP_DIR = os.path.join(PROJECT_DIR, "data", "oai_dc_20260405")

# Compact bundle the app prefers when present (built by build_data.py)
BUNDLE_DIR = os.path.join(APP_DIR, "data")
RECORDS_PARQUET = os.path.join(BUNDLE_DIR, "records.parquet")
BACKUP_IDS_PARQUET = os.path.join(BUNDLE_DIR, "backup_ids.parquet")

COMBINED_SETS = ["etds", "pubs", "oers", "arch"]

# Community-level / container sets — skipped when picking a record's primary series
CONTAINER_SETS = {
    "al", "bb", "bc", "bm", "bx", "cc", "cl", "cm", "cw", "dsi", "gc", "gj",
    "hc", "ho", "jj", "kb", "lacuny", "le", "lg", "me", "mhc", "nc", "ny",
    "oaa", "qb", "qc", "si", "slu", "sph", "sps", "ufs", "yc",
    "bb_arch", "bc_arch", "bx_arch", "cc_arch", "gc_arch_all", "ho_arch",
    "jj_arch", "kb_arch", "lg_arch", "nc_arch", "ny_arch", "qc_arch",
    "si_arch", "yc_arch", "le_arch", "dsi_arch",
    "centers", "etds", "pubs", "oers", "arch",
    "gc_etds_all", "sph_etds_all",
}

SCHOOL_MAP = {
    "al": "CUNY Central Office",
    "bb": "Baruch College",
    "bc": "Brooklyn College",
    "bm": "Borough of Manhattan CC",
    "bx": "Bronx CC",
    "cc": "City College of New York",
    "cl": "CUNY School of Law",
    "cm": "CUNY School of Medicine",
    "cpr": "Center for Puerto Rican Studies",
    "cw": "CUNY-wide",
    "dsi": "Dominican Studies Institute",
    "gc": "Graduate Center",
    "gj": "Newmark Graduate School of Journalism",
    "hc": "Hunter College",
    "ho": "Hostos CC",
    "jj": "John Jay College",
    "kb": "Kingsborough CC",
    "lacuny": "LACUNY",
    "le": "Lehman College",
    "lg": "LaGuardia CC",
    "me": "Medgar Evers College",
    "mhc": "Macaulay Honors College",
    "msi": "Mexican Studies Institute",
    "nc": "Guttman CC",
    "ny": "City Tech",
    "oaa": "Office of Academic Affairs",
    "qb": "Queensborough CC",
    "qc": "Queens College",
    "si": "College of Staten Island",
    "slu": "School of Labor and Urban Studies",
    "sph": "School of Public Health",
    "sps": "School of Professional Studies",
    "ufs": "University Faculty Senate",
    "yc": "York College",
}


def _series_to_school(series: str) -> str:
    """Return a human-readable school name for a series spec like 'gc_etds'."""
    parts = series.split("_")
    for n in (3, 2, 1):
        candidate = "_".join(parts[:n])
        if candidate in SCHOOL_MAP:
            return SCHOOL_MAP[candidate]
    prefix = parts[0]
    return SCHOOL_MAP.get(prefix, prefix)


def _parse_record(record_elem) -> dict:
    """Pull the fields we care about out of one <oai:record>."""
    ident_elem = record_elem.find(f".//{{{OAI_NS}}}identifier")
    identifier = ident_elem.text if ident_elem is not None else ""

    title_elem = record_elem.find(f".//{{{DC_NS}}}title")
    title = (title_elem.text or "").strip() if title_elem is not None else ""

    date_elem = record_elem.find(f".//{{{DC_NS}}}date")
    date = (date_elem.text or "").strip()[:10] if date_elem is not None else ""

    source_elem = record_elem.find(f".//{{{DC_NS}}}source")
    source = (source_elem.text or "").strip() if source_elem is not None else ""

    type_elem = record_elem.find(f".//{{{DC_NS}}}type")
    doc_type = (type_elem.text or "").strip() if type_elem is not None else ""

    authors = []
    for c in record_elem.iter(f"{{{DC_NS}}}creator"):
        if c.text and c.text.strip():
            authors.append(c.text.strip())

    return {
        "identifier": identifier,
        "title": title,
        "date": date,
        "source": source,
        "type": doc_type,
        "authors": "; ".join(authors),
    }


def _file_records(filepath: str):
    """Yield parsed record dicts from one XML file."""
    try:
        tree = ET.parse(filepath)
    except ET.ParseError:
        return
    for record in tree.getroot().iter(f"{{{OAI_NS}}}record"):
        yield _parse_record(record)


def _series_from_filename(filename: str) -> str:
    return filename.replace("publication_", "").replace(".xml", "")


@st.cache_data(show_spinner="Loading records...")
def load_records(data_dir: str = DATA_DIR) -> pd.DataFrame:
    """Build one row per unique record from the Parquet bundle, or from XML."""
    if os.path.exists(RECORDS_PARQUET):
        return pd.read_parquet(RECORDS_PARQUET)

    record_data = {}      # identifier -> dict of fields
    record_series = defaultdict(set)  # identifier -> set of series it appears in

    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith(".xml"):
            continue
        series = _series_from_filename(filename)
        filepath = os.path.join(data_dir, filename)
        for rec in _file_records(filepath):
            ident = rec["identifier"]
            if not ident:
                continue
            if ident not in record_data:
                record_data[ident] = rec
            record_series[ident].add(series)

    rows = []
    for ident, rec in record_data.items():
        all_series = record_series[ident]
        non_container = [s for s in all_series if s not in CONTAINER_SETS]
        if non_container:
            primary = sorted(non_container, key=lambda s: (-len(s), s))[0]
        else:
            primary = sorted(all_series, key=lambda s: (-len(s), s))[0]

        manuscript_id_match = re.search(r"-(\d+)$", ident)
        manuscript_id = manuscript_id_match.group(1) if manuscript_id_match else ""

        year = ""
        if rec["date"]:
            year_match = re.match(r"(\d{4})", rec["date"])
            year = year_match.group(1) if year_match else ""

        rows.append({
            "identifier": ident,
            "manuscript_id": manuscript_id,
            "series": primary,
            "school": _series_to_school(primary),
            "title": rec["title"],
            "authors": rec["authors"],
            "date": rec["date"],
            "year": year,
            "source": rec["source"],
            "type": rec["type"],
            "in_etds": "etds" in all_series,
            "in_pubs": "pubs" in all_series,
            "in_oers": "oers" in all_series,
            "in_arch": "arch" in all_series,
        })

    return pd.DataFrame(rows)


@st.cache_data(show_spinner="Comparing harvests...")
def load_backup_identifiers(backup_dir: str = BACKUP_DIR) -> set:
    """Return the set of OAI identifiers present in a prior harvest."""
    if os.path.exists(BACKUP_IDS_PARQUET):
        return set(pd.read_parquet(BACKUP_IDS_PARQUET)["identifier"])
    if not os.path.isdir(backup_dir):
        return set()
    ids = set()
    for filename in sorted(os.listdir(backup_dir)):
        if not filename.endswith(".xml"):
            continue
        try:
            tree = ET.parse(os.path.join(backup_dir, filename))
        except ET.ParseError:
            continue
        for ident_elem in tree.getroot().iter(f"{{{OAI_NS}}}identifier"):
            if ident_elem.text:
                ids.add(ident_elem.text)
    return ids


def harvest_timestamp(data_dir: str = DATA_DIR) -> str:
    """Return a human-readable timestamp from when the data was last harvested."""
    if os.path.exists(RECORDS_PARQUET):
        latest = os.path.getmtime(RECORDS_PARQUET)
        return pd.Timestamp(latest, unit="s").strftime("%B %-d, %Y")
    if not os.path.isdir(data_dir):
        return "unknown"
    files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".xml")]
    if not files:
        return "unknown"
    latest = max(os.path.getmtime(f) for f in files)
    return pd.Timestamp(latest, unit="s").strftime("%B %-d, %Y")
