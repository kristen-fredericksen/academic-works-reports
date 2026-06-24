"""
OAI-PMH Harvester for CUNY Academic Works

Downloads XML records from all sets in two metadata formats (oai_dc and qdc).
Handles resumption tokens for large sets, skips already-downloaded files,
and provides progress logging.

Usage:
    python3 src/harvest.py                    # Harvest all sets
    python3 src/harvest.py --sets al bb_pubs  # Harvest specific sets only
    python3 src/harvest.py --force            # Re-download even if files exist
"""

import argparse
import os
import time
import xml.etree.ElementTree as ET

import requests

# ── Configuration ──────────────────────────────────────────────────────────

BASE_URL = "https://academicworks.cuny.edu/do/oai/"
METADATA_PREFIXES = ["oai_dc", "qdc"]
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REQUEST_DELAY = 1  # seconds between requests

# OAI-PMH XML namespace
OAI_NS = "http://www.openarchives.org/OAI/2.0/"

# Register namespaces so ElementTree uses clean prefixes instead of ns0, ns1
ET.register_namespace("oai", OAI_NS)
ET.register_namespace("oai_dc", "http://www.openarchives.org/OAI/2.0/oai_dc/")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
ET.register_namespace("dcterms", "http://purl.org/dc/terms/")
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")


# ── OAI-PMH helpers ───────────────────────────────────────────────────────

def oai_request(params: dict) -> ET.Element:
    """Make an OAI-PMH request and return the parsed XML root element."""
    response = requests.get(BASE_URL, params=params, timeout=120)
    response.raise_for_status()
    return ET.fromstring(response.content)


def get_sets() -> list[tuple[str, str]]:
    """
    Fetch all available sets from the OAI-PMH endpoint.
    Returns a list of (setSpec, setName) tuples.
    """
    sets = []
    params = {"verb": "ListSets"}

    while True:
        root = oai_request(params)

        list_sets_el = root.find(f"{{{OAI_NS}}}ListSets")
        if list_sets_el is None:
            break

        for set_el in list_sets_el.findall(f"{{{OAI_NS}}}set"):
            spec = set_el.findtext(f"{{{OAI_NS}}}setSpec", "")
            name = set_el.findtext(f"{{{OAI_NS}}}setName", "")
            if spec:
                sets.append((spec, name))

        # Check for resumption token (ListSets can be paginated too)
        token_el = list_sets_el.find(f"{{{OAI_NS}}}resumptionToken")
        if token_el is not None and token_el.text:
            params = {"verb": "ListSets", "resumptionToken": token_el.text}
            time.sleep(REQUEST_DELAY)
        else:
            break

    return sets


def harvest_set(set_spec: str, metadata_prefix: str) -> list[ET.Element]:
    """
    Harvest all records for a given set and metadata prefix.
    Follows resumption tokens until all pages are retrieved.

    Returns a list of <record> elements.
    """
    records = []
    page = 0
    params = {
        "verb": "ListRecords",
        "set": set_spec,
        "metadataPrefix": metadata_prefix,
    }

    while True:
        page += 1
        root = oai_request(params)

        # Check for OAI-PMH error (e.g., noRecordsMatch)
        error_el = root.find(f"{{{OAI_NS}}}error")
        if error_el is not None:
            code = error_el.get("code", "")
            if code == "noRecordsMatch":
                return []
            else:
                raise RuntimeError(
                    f"OAI-PMH error for {set_spec} ({metadata_prefix}): "
                    f"{code} - {error_el.text}"
                )

        list_records_el = root.find(f"{{{OAI_NS}}}ListRecords")
        if list_records_el is None:
            break

        page_records = list_records_el.findall(f"{{{OAI_NS}}}record")
        records.extend(page_records)

        if page > 1 or len(page_records) > 0:
            print(f"    Page {page}: {len(page_records)} records "
                  f"(total so far: {len(records)})")

        # Check for resumption token
        token_el = list_records_el.find(f"{{{OAI_NS}}}resumptionToken")
        if token_el is not None and token_el.text:
            params = {
                "verb": "ListRecords",
                "resumptionToken": token_el.text,
            }
            time.sleep(REQUEST_DELAY)
        else:
            break

    return records


def save_records(records: list[ET.Element], filepath: str) -> None:
    """Save a list of <record> elements to a single XML file."""
    # Build a wrapper document
    root = ET.Element("records")
    root.text = "\n"

    for record in records:
        root.append(record)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    tree.write(filepath, encoding="unicode", xml_declaration=True)


def safe_filename(set_spec: str) -> str:
    """Convert a set spec like 'publication:bb_pubs' to 'publication_bb_pubs.xml'."""
    return set_spec.replace(":", "_") + ".xml"


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Harvest OAI-PMH records from CUNY Academic Works"
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        help="Harvest only these sets (use short codes like 'al', 'bb_pubs'). "
             "The 'publication:' prefix is added automatically.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if output files already exist",
    )
    parser.add_argument(
        "--prefixes",
        nargs="+",
        choices=METADATA_PREFIXES,
        default=METADATA_PREFIXES,
        help="Which metadata prefixes to harvest (default: both oai_dc and qdc)",
    )
    args = parser.parse_args()

    # Step 1: Get available sets
    print("Fetching available sets from OAI-PMH...")
    all_sets = get_sets()
    print(f"Found {len(all_sets)} sets.\n")

    # Filter to requested sets if specified
    if args.sets:
        # Add 'publication:' prefix if not already present
        requested = set()
        for s in args.sets:
            if ":" in s:
                requested.add(s)
            else:
                requested.add(f"publication:{s}")

        sets_to_harvest = [(spec, name) for spec, name in all_sets if spec in requested]

        not_found = requested - {spec for spec, _ in sets_to_harvest}
        if not_found:
            print(f"Warning: these sets were not found: {', '.join(sorted(not_found))}")

        print(f"Harvesting {len(sets_to_harvest)} of {len(all_sets)} sets.\n")
    else:
        sets_to_harvest = all_sets

    # Step 2: Harvest each set in each format
    summary: dict[str, dict] = {}  # {prefix: {set_spec: record_count or error}}

    for prefix in args.prefixes:
        summary[prefix] = {}
        print(f"{'='*60}")
        print(f"METADATA PREFIX: {prefix}")
        print(f"{'='*60}\n")

        # Create output directory once per prefix
        os.makedirs(os.path.join(DATA_DIR, prefix), exist_ok=True)

        for i, (set_spec, set_name) in enumerate(sets_to_harvest, 1):
            filename = safe_filename(set_spec)
            filepath = os.path.join(DATA_DIR, prefix, filename)

            # Skip if already downloaded
            if os.path.exists(filepath) and not args.force:
                print(f"[{i}/{len(sets_to_harvest)}] {set_spec} ({set_name}) "
                      f"- SKIPPED (file exists)")
                summary[prefix][set_spec] = "skipped"
                continue

            print(f"[{i}/{len(sets_to_harvest)}] {set_spec} ({set_name})")

            try:
                records = harvest_set(set_spec, prefix)

                if not records:
                    print("    No records found.\n")
                    summary[prefix][set_spec] = 0
                    continue

                save_records(records, filepath)
                print(f"    Saved {len(records)} records to {filepath}\n")
                summary[prefix][set_spec] = len(records)

            except Exception as e:
                print(f"    ERROR: {e}\n")
                summary[prefix][set_spec] = f"error: {e}"

            time.sleep(REQUEST_DELAY)

    # Step 3: Print summary
    print(f"\n{'='*60}")
    print("HARVEST SUMMARY")
    print(f"{'='*60}\n")

    for prefix in args.prefixes:
        results = summary[prefix]
        record_counts = [v for v in results.values() if isinstance(v, int)]
        errors = [k for k, v in results.items()
                  if isinstance(v, str) and v.startswith("error")]
        skipped = [k for k, v in results.items() if v == "skipped"]
        empty = [k for k, v in results.items() if v == 0]

        total_records = sum(record_counts)
        sets_with_records = sum(1 for c in record_counts if c > 0)

        print(f"{prefix}:")
        print(f"  Total records downloaded: {total_records:,}")
        print(f"  Sets with records: {sets_with_records}")
        print(f"  Empty sets: {len(empty)}")
        print(f"  Skipped (already downloaded): {len(skipped)}")
        if errors:
            print(f"  Errors ({len(errors)}):")
            for set_spec in errors:
                print(f"    - {set_spec}: {results[set_spec]}")
        print()


if __name__ == "__main__":
    main()
