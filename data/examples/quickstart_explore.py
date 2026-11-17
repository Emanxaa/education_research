"""
Quickstart script for the J2-T1 Master Data Repository.
Run from inside `data/` or `data/examples/` to verify SHA-256 checksums
and inspect Track A (2020-2023) and Track B (2022-2023) weighted patterns.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1]
SQLITE_PATH = DATA_DIR / "master_j2_t1_digital_learning.sqlite"
CHECKSUM_PATH = DATA_DIR / "checksums_sha256.txt"


def verify_checksums() -> None:
    if not CHECKSUM_PATH.exists():
        print("checksums_sha256.txt not found; skipping integrity check.")
        return
    print("=== 1. VERIFIKASI INTEGRITAS FILE (SHA-256) ===")
    for line in CHECKSUM_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected_hash, rel_name = line.strip().split(maxsplit=1)
        target = DATA_DIR / rel_name
        h = hashlib.sha256()
        with open(target, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
        status = "OK" if actual == expected_hash else "MISMATCH"
        print(f"  [{status}] {rel_name}")
        assert actual == expected_hash, f"Checksum mismatch on {rel_name}"


def main() -> None:
    verify_checksums()

    with sqlite3.connect(SQLITE_PATH) as conn:
        print("\n=== 2. TREN TRACK A BERDASARKAN PERANGKAT TIK (2020-2023, FORMAL) ===")
        q_dev = """
        SELECT tahun, device_tier,
               COUNT(*) AS n_sampel,
               ROUND(SUM(weind * online_learning) / SUM(weind) * 100.0, 2) AS online_learning_pct,
               ROUND(SUM(weind * ict_literacy) / SUM(weind) * 100.0, 2) AS ict_literacy_pct
        FROM fact_secondary_students
        WHERE in_track_a_formal = 1
        GROUP BY tahun, device_tier
        ORDER BY tahun, device_tier
        """
        print(pd.read_sql_query(q_dev, conn).to_string(index=False))

        print("\n=== 3. TOP 5 & BOTTOM 5 KAB/KOTA ICT LITERACY 2023 (TRACK B) ===")
        df_23 = pd.read_sql_query(
            """
            SELECT kode_bps, nama_wilayah_std, tipe_wilayah, n_students_formal,
                   weighted_online_learning_pct, weighted_ict_literacy_pct, weighted_pc_laptop_pct
            FROM agg_kabkota_wave_summary
            WHERE tahun = 2023
            ORDER BY weighted_ict_literacy_pct DESC
            """,
            conn,
        )
        print("-- Top 5 ICT Literacy 2023 --")
        print(df_23.head(5).to_string(index=False))
        print("-- Bottom 5 ICT Literacy 2023 --")
        print(df_23.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
