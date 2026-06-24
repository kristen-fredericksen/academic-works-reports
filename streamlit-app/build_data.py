"""Convert harvested XML into a compact Parquet bundle for the Streamlit app.

Run this after each harvest. The app loads from these Parquet files, not from
the raw XML, so the deployed repo stays small.
"""

import os
import sys

# Make the app's modules importable when running this script directly
sys.path.insert(0, os.path.dirname(__file__))

from data_loader import (
    BACKUP_DIR,
    DATA_DIR,
    load_backup_identifiers,
    load_records,
)

# Where the Parquet bundle goes — inside the app folder so it ships with deploys
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
RECORDS_PATH = os.path.join(OUT_DIR, "records.parquet")
BACKUP_IDS_PATH = os.path.join(OUT_DIR, "backup_ids.parquet")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Reading XML from {DATA_DIR}...")
    df = load_records.__wrapped__(DATA_DIR)
    print(f"  {len(df):,} unique records")

    df.to_parquet(RECORDS_PATH, compression="zstd", index=False)
    size_mb = os.path.getsize(RECORDS_PATH) / 1024 / 1024
    print(f"Wrote {RECORDS_PATH} ({size_mb:.1f} MB)")

    print(f"\nReading backup identifiers from {BACKUP_DIR}...")
    ids = load_backup_identifiers.__wrapped__(BACKUP_DIR)
    if ids:
        import pandas as pd
        pd.DataFrame({"identifier": sorted(ids)}).to_parquet(
            BACKUP_IDS_PATH, compression="zstd", index=False
        )
        size_kb = os.path.getsize(BACKUP_IDS_PATH) / 1024
        print(f"  {len(ids):,} identifiers")
        print(f"Wrote {BACKUP_IDS_PATH} ({size_kb:.0f} KB)")
    else:
        print(f"  No backup found, skipping")


if __name__ == "__main__":
    main()
