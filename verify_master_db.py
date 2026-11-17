"""
Independent Verification Suite for J2-T1 Master Database.
Checks SQLite vs Parquet parity, relational integrity, PRD success criteria,
and descriptive summaries across Track A (2020-2023) and Track B (2022-2023).
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify J2-T1 Master Database integrity and parity.")
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory containing master_j2_t1_digital_learning.sqlite and CSV/CSV.GZ exports (default: ./data)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    sqlite_path = data_dir / "master_j2_t1_digital_learning.sqlite"
    assert sqlite_path.exists(), f"Missing SQLite DB at {sqlite_path}"

    with sqlite3.connect(sqlite_path) as conn:
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn
        )["name"].tolist()
        expected_tables = [
            "agg_kabkota_wave_summary",
            "dim_gelombang",
            "dim_wilayah",
            "fact_household_context",
            "fact_secondary_students",
            "qa_audit_log",
        ]
        assert tables == expected_tables, f"Unexpected tables: {tables}"

        # Verify SQLite vs CSV/CSV.GZ row-count parity
        df_stu_sql = pd.read_sql_query("SELECT * FROM fact_secondary_students", conn)
        df_stu_csv = pd.read_csv(data_dir / "fact_secondary_students.csv")
        assert len(df_stu_sql) == len(df_stu_csv)

        df_hh_sql = pd.read_sql_query("SELECT * FROM fact_household_context", conn)
        df_hh_csv = pd.read_csv(data_dir / "fact_household_context.csv.gz")
        assert len(df_hh_sql) == len(df_hh_csv)

        # Verify FK integrity via SQL JOIN
        orphan_stu = pd.read_sql_query(
            """
            SELECT COUNT(*) AS n_orphans
            FROM fact_secondary_students s
            LEFT JOIN fact_household_context h ON s.hh_uid = h.hh_uid
            WHERE h.hh_uid IS NULL
            """,
            conn,
        ).iloc[0]["n_orphans"]
        assert orphan_stu == 0, f"Found {orphan_stu} orphan students"

        bad_wilayah = pd.read_sql_query(
            """
            SELECT COUNT(*) AS n_bad
            FROM fact_secondary_students s
            LEFT JOIN dim_wilayah w ON s.kode_bps = w.kode_bps
            WHERE w.kode_bps IS NULL
            """,
            conn,
        ).iloc[0]["n_bad"]
        assert bad_wilayah == 0, f"Found {bad_wilayah} unmapped wilayah rows"

        qa_log = pd.read_sql_query("SELECT * FROM qa_audit_log", conn)
        assert (qa_log["status"] == "PASS").all(), f"QA Failures:\n{qa_log[qa_log['status']!='PASS']}"

        # Track A & Track B cross-tab checks
        track_a_tier = pd.read_sql_query(
            """
            SELECT tahun, school_tier,
                   COUNT(*) AS n,
                   ROUND(SUM(weind * online_learning) / SUM(weind) * 100.0, 2) AS ol_pct
            FROM fact_secondary_students
            WHERE is_formal_secondary = 1
            GROUP BY tahun, school_tier
            ORDER BY tahun, school_tier
            """,
            conn,
        )

        track_b_sector = pd.read_sql_query(
            """
            SELECT tahun, school_sector, school_tier,
                   COUNT(*) AS n,
                   ROUND(SUM(weind * online_learning) / SUM(weind) * 100.0, 2) AS ol_pct,
                   ROUND(SUM(weind * ict_literacy) / SUM(weind) * 100.0, 2) AS ict_pct
            FROM fact_secondary_students
            WHERE is_formal_secondary = 1 AND tahun IN (2022, 2023)
            GROUP BY tahun, school_sector, school_tier
            ORDER BY tahun, school_tier, school_sector
            """,
            conn,
        )

        age_outliers = pd.read_sql_query(
            """
            SELECT is_formal_secondary,
                   COUNT(*) AS n,
                   MIN(age) AS min_age,
                   MAX(age) AS max_age,
                   SUM(CASE WHEN is_typical_age_11_19 = 0 THEN 1 ELSE 0 END) AS outside_11_19
            FROM fact_secondary_students
            GROUP BY is_formal_secondary
            """,
            conn,
        )

    print("ALL ASSERTIONS PASSED!")
    print("\n=== TRACK A: FORMAL SECONDARY BY TIER (2020-2023) ===")
    print(track_a_tier.to_string(index=False))
    print("\n=== TRACK B: FORMAL SECONDARY BY SECTOR & TIER (2022-2023) ===")
    print(track_b_sector.to_string(index=False))
    print("\n=== AGE DISTRIBUTION AUDIT (FORMAL vs NON-FORMAL) ===")
    print(age_outliers.to_string(index=False))


if __name__ == "__main__":
    main()
