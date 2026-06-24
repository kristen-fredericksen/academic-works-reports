"""
Find records that appear in school-level sets but are missing from the
combined cross-institution sets (publication:etds, publication:pubs,
publication:oers).

Usage:
    python3 src/find_missing_records.py
    python3 src/find_missing_records.py --sets etds pubs
    python3 src/find_missing_records.py --sets oers
"""

import argparse
import os
import xml.etree.ElementTree as ET

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
DC_NS = "http://purl.org/dc/elements/1.1/"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "oai_dc")

# Combined sets and the suffix used by their school-level counterparts
COMBINED_SETS = {
    "etds": "publication_etds.xml",
    "pubs": "publication_pubs.xml",
    "oers": "publication_oers.xml",
}


def get_records(filepath: str) -> dict[str, str]:
    """Return {identifier: title} for every record in an OAI-PMH XML file."""
    records = {}
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as e:
        print(f"  ERROR parsing {filepath}: {e}")
        return records

    root = tree.getroot()
    for record in root.iter(f"{{{OAI_NS}}}record"):
        ident_elem = record.find(f".//{{{OAI_NS}}}identifier")
        title_elem = record.find(f".//{{{DC_NS}}}title")
        ident = ident_elem.text if ident_elem is not None else "unknown"
        title = (
            title_elem.text.strip()
            if title_elem is not None and title_elem.text
            else "(no title)"
        )
        records[ident] = title
    return records


def find_school_files(set_type: str, combined_filename: str) -> list[str]:
    """Return sorted list of school-level filenames for a given set type.

    For example, set_type='pubs' returns files like publication_bb_pubs.xml
    but not publication_pubs.xml (the combined set itself).
    """
    suffix = f"_{set_type}.xml"
    school_files = []
    for filename in sorted(os.listdir(DATA_DIR)):
        if filename == combined_filename:
            continue
        if filename.endswith(suffix) and filename.startswith("publication_"):
            school_files.append(filename)
    return school_files


def analyze_set(set_type: str) -> dict:
    """Compare one combined set against its school-level sets.

    Returns a summary dict with totals and per-file missing records.
    """
    combined_filename = COMBINED_SETS[set_type]
    combined_path = os.path.join(DATA_DIR, combined_filename)
    combined_records = get_records(combined_path)
    combined_ids = set(combined_records.keys())

    school_files = find_school_files(set_type, combined_filename)

    results = []
    total_missing = 0

    for filename in school_files:
        filepath = os.path.join(DATA_DIR, filename)
        school_records = get_records(filepath)
        school_ids = set(school_records.keys())
        missing_ids = school_ids - combined_ids

        if missing_ids:
            set_name = filename.replace("publication_", "").replace(".xml", "")
            missing_details = [
                (ident, school_records[ident]) for ident in sorted(missing_ids)
            ]
            results.append({
                "set_name": set_name,
                "total_in_set": len(school_records),
                "missing_count": len(missing_ids),
                "missing_records": missing_details,
            })
            total_missing += len(missing_ids)

    return {
        "set_type": set_type,
        "combined_count": len(combined_records),
        "total_missing": total_missing,
        "school_results": results,
    }


def print_report(summary: dict) -> None:
    """Print a readable report for one combined set."""
    set_type = summary["set_type"]
    combined_count = summary["combined_count"]
    total_missing = summary["total_missing"]

    print("=" * 70)
    print(f"MISSING FROM publication:{set_type} ({combined_count:,} records)")
    print("=" * 70)

    if not summary["school_results"]:
        print("\n  No missing records found.\n")
        return

    for result in summary["school_results"]:
        print(
            f"\n  {result['set_name']} ({result['total_in_set']:,} records) "
            f"— {result['missing_count']} missing:"
        )
        for ident, title in result["missing_records"]:
            # Truncate long titles for readability
            if len(title) > 90:
                title = title[:87] + "..."
            print(f"    {ident}")
            print(f"      {title}")

    print(f"\n  TOTAL missing from publication:{set_type}: {total_missing}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Find records in school-level sets missing from combined sets."
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        choices=list(COMBINED_SETS.keys()),
        default=list(COMBINED_SETS.keys()),
        help="Which combined sets to check (default: all three)",
    )
    args = parser.parse_args()

    # Show combined set sizes
    for set_type in args.sets:
        filepath = os.path.join(DATA_DIR, COMBINED_SETS[set_type])
        records = get_records(filepath)
        print(f"Combined publication:{set_type} — {len(records):,} records")
    print()

    # Run analysis and print reports
    for set_type in args.sets:
        summary = analyze_set(set_type)
        print_report(summary)


if __name__ == "__main__":
    main()
