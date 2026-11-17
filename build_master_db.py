"""
Master Database Builder for J2-T1:
The Post-Pandemic Digital Learning Divide (SUSENAS West Java 2020-2023).

Executes column-projected (lazy) ingestion across 2020-2023 waves,
applies verified questionnaire crosswalks, validates Pydantic data contracts,
builds SQLite relational Master DB + Parquet analytical marts,
and outputs a Data Dictionary and QA Audit Report.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError

# ------------------------------------------------------------------------------
# Paths & Configuration
# ------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUSENAS_ROOT = Path(r"D:\IPB\KULIAH\S1\SD\Tugas\SUSENAS\JAWA BARAT")
MASTER_WILAYAH_PATH = PROJECT_ROOT / "infografis" / "catalog" / "master_wilayah.json"
OUT_DIR = Path(__file__).resolve().parent / "data"
SQLITE_PATH = OUT_DIR / "master_j2_t1_digital_learning.sqlite"

WAVES = [2020, 2021, 2022, 2023]

YEAR_SCHEMA_MAP: Dict[int, Dict[str, Optional[str]]] = {
    2020: {
        "hh_key": "RENUM",
        "attending_col": "R612",
        "level_col": "R613",
        "sector_col": None,
        "prev_attending_col": "R618",
        "ijazah_col": "R615",
        "kip_col": "R616",
        "pip_col": "R617",
        "ol_col": "R811_B",
        "ol_marker": "B",
        "ict_col": None,
    },
    2021: {
        "hh_key": "RENUM",
        "attending_col": "R612",
        "level_col": "R613",
        "sector_col": None,
        "prev_attending_col": "R618",
        "ijazah_col": "R615",
        "kip_col": "R616",
        "pip_col": "R617",
        "ol_col": "R811_B",
        "ol_marker": "B",
        "ict_col": None,
    },
    2022: {
        "hh_key": "URUT",
        "attending_col": "R610",
        "level_col": "R612",
        "sector_col": "R611",
        "prev_attending_col": "R620",
        "ijazah_col": "R614",
        # Verified in 2022 metadata: R615=subsidi kuota internet, R616=KIP {1,2,5}, R617=PIP {1,5}
        "kip_col": "R616",
        "pip_col": "R617",
        "ol_col": "R811_H",
        "ol_marker": "H",
        "ict_col": "R812",
    },
    2023: {
        "hh_key": "URUT",
        "attending_col": "R610",
        "level_col": "R612",
        "sector_col": "R611",
        "prev_attending_col": "R619",
        "ijazah_col": "R614",
        "kip_col": "R615",
        "pip_col": "R616",
        "ol_col": "R811_H",
        "ol_marker": "H",
        "ict_col": "R812",
    },
}

LEVEL_MAP_2020_2021: Dict[str, Tuple[str, str, int]] = {
    "5": ("Paket B", "Junior_Secondary", 0),
    "6": ("SMPLB", "Junior_Secondary", 0),
    "7": ("SMP", "Junior_Secondary", 1),
    "8": ("MTs", "Junior_Secondary", 1),
    "9": ("Paket C", "Senior_General", 0),
    "10": ("SMLB", "Senior_General", 0),
    "11": ("SMA", "Senior_General", 1),
    "12": ("MA", "Senior_General", 1),
    "13": ("SMK", "Senior_Vocational", 1),
    "14": ("MAK", "Senior_Vocational", 1),
}

LEVEL_MAP_2022_2023: Dict[str, Tuple[str, str, int]] = {
    "6": ("Paket B", "Junior_Secondary", 0),
    "7": ("SMPLB", "Junior_Secondary", 0),
    "8": ("SMP", "Junior_Secondary", 1),
    "9": ("MTs", "Junior_Secondary", 1),
    "10": ("SPM_Wustha", "Junior_Secondary", 0),
    "11": ("Paket C", "Senior_General", 0),
    "12": ("SMLB", "Senior_General", 0),
    "13": ("SMA", "Senior_General", 1),
    "14": ("MA", "Senior_General", 1),
    "15": ("SMK", "Senior_Vocational", 1),
    "16": ("MAK", "Senior_Vocational", 1),
    "17": ("SPM_Ulya", "Senior_General", 0),
}


# ------------------------------------------------------------------------------
# Pydantic Data Contracts (Tier 1 Validation)
# ------------------------------------------------------------------------------
class StudentRecordContract(BaseModel):
    student_uid: str = Field(..., min_length=6)
    hh_uid: str = Field(..., min_length=5)
    tahun: Literal[2020, 2021, 2022, 2023]
    kode_bps: str = Field(..., pattern=r"^32(0[1-9]|1[0-8]|7[1-9])$")
    r105_urban: Literal[0, 1]
    strata_code: int = Field(..., ge=11, le=792)
    psu_wi1: str = Field(..., min_length=1)
    weind: float = Field(..., gt=0.0)
    weind_norm_wave: float = Field(..., gt=0.0)
    age: int = Field(..., ge=5, le=99)
    female: Literal[0, 1]
    school_tier: Literal["Junior_Secondary", "Senior_General", "Senior_Vocational"]
    is_formal_secondary: Literal[0, 1]
    online_learning: Literal[0, 1]
    ict_literacy: Optional[Literal[0, 1]] = None
    has_computer_device: Literal[0, 1]
    device_tier: Literal["None", "HP_Only", "PC_Laptop_Tablet"]
    kapita: float = Field(..., gt=0.0)
    exp_quintile: int = Field(..., ge=1, le=5)


class WilayahWaveContract(BaseModel):
    tahun: Literal[2020, 2021, 2022, 2023]
    kode_bps: str = Field(..., pattern=r"^32(0[1-9]|1[0-8]|7[1-9])$")
    n_students_formal: int = Field(..., gt=0)
    weighted_online_learning_pct: float = Field(..., ge=0.0, le=100.0)
    kish_n_eff: float = Field(..., gt=0.0)


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def map_ijazah(code_str: str, year: int) -> str:
    """Harmonize highest certificate code across 2020-2021 vs 2022-2023."""
    if not code_str or not code_str.isdigit():
        return "Unknown"
    c = int(code_str)
    if year in (2020, 2021):
        if c == 22 or c == 0:
            return "No_Primary"
        if 1 <= c <= 4:
            return "Primary_SD"
        if 5 <= c <= 8:
            return "Junior_SMP"
        if 9 <= c <= 14:
            return "Senior_SMA_SMK"
        if 15 <= c <= 21:
            return "Tertiary_Univ"
        return "Unknown"
    if c == 25 or c == 0:
        return "No_Primary"
    if 1 <= c <= 5:
        return "Primary_SD"
    if 6 <= c <= 10:
        return "Junior_SMP"
    if 11 <= c <= 17:
        return "Senior_SMA_SMK"
    if 18 <= c <= 24:
        return "Tertiary_Univ"
    return "Unknown"


def weighted_quintile(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Assign 1..5 weighted expenditure quintiles within a single survey wave."""
    order = np.argsort(values, kind="mergesort")
    sorted_w = weights[order]
    cum_w = np.cumsum(sorted_w) / np.sum(sorted_w)
    # Assign 1..5 using strict cumulative share boundaries
    q_sorted = np.minimum(5, (np.floor(cum_w * 5.0 - 1e-12)).astype(int) + 1)
    q_sorted = np.maximum(1, q_sorted)
    out = np.empty_like(q_sorted)
    out[order] = q_sorted
    return out


def weighted_mean_and_se(vals: np.ndarray, w: np.ndarray) -> Tuple[float, float, float]:
    """Return weighted proportion/mean, Kish effective N, and approximate SE."""
    w_sum = float(np.sum(w))
    if w_sum <= 0:
        return float("nan"), 0.0, float("nan")
    p = float(np.sum(w * vals) / w_sum)
    n_eff = float((w_sum ** 2) / np.sum(w ** 2))
    se = math.sqrt(max(0.0, p * (1.0 - p)) / max(1.0, n_eff))
    return p, n_eff, se


def find_wave_files(year: int) -> Tuple[Path, Path, Path]:
    """Locate KOR IND PART1, KOR RT, and KP BP 4.3 CSV paths for a wave."""
    yr_dir = SUSENAS_ROOT / str(year) / "csv"
    ind_files = sorted((yr_dir / "KOR").glob("*PART1*.csv"))
    rt_files = sorted((yr_dir / "KOR").glob("*Rumah Tangga*.csv"))
    kp_files = sorted(yr_dir.glob("Modul KP*/*4.3*.csv"))
    if not ind_files or not rt_files or not kp_files:
        raise FileNotFoundError(f"Missing required CSVs for wave {year} in {yr_dir}")
    return ind_files[0], rt_files[0], kp_files[0]


def load_dim_wilayah() -> pd.DataFrame:
    """Load canonical 27 West Java regencies/cities from master_wilayah.json."""
    with open(MASTER_WILAYAH_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rows = []
    for item in payload["kabupaten_kota_jabar"]:
        kode_bps = str(item["kode_bps"])
        rows.append(
            {
                "kode_r102": int(kode_bps[2:]),
                "kode_bps": kode_bps,
                "kode_kemendagri": str(item["kode_kemendagri"]),
                "nama_wilayah_std": str(item["nama"]),
                "tipe_wilayah": str(item["tipe"]),
            }
        )
    return pd.DataFrame(rows).sort_values("kode_bps").reset_index(drop=True)


def process_wave(year: int, dim_wilayah: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Lazily read needed columns for one wave and return (hh_df, students_df, wave_stats)."""
    cfg = YEAR_SCHEMA_MAP[year]
    hh_key = cfg["hh_key"]
    ind_path, rt_path, kp_path = find_wave_files(year)

    # 1. Read KOR RT (projected columns only)
    rt_cols = [hh_key, "R102", "R105", "WI1", "R301", "R1816", "R2001F", "R2204A", "FWT"]
    df_rt = pd.read_csv(rt_path, usecols=rt_cols, dtype=str, keep_default_na=False)

    # 2. Read KP 4.3 (projected columns only)
    kp_cols = [hh_key, "FOOD", "NONFOOD", "EXPEND", "KAPITA", "WERT", "WEIND"]
    df_kp = pd.read_csv(kp_path, usecols=kp_cols, dtype=str, keep_default_na=False)

    # 3. Read KOR IND PART1 (projected columns only)
    ind_cols = [
        hh_key, "R102", "R105", "WI1", "R401", "R403", "R405", "R407", "FWT",
        cfg["attending_col"], cfg["level_col"], cfg["prev_attending_col"],
        cfg["ijazah_col"], cfg["kip_col"], cfg["pip_col"],
        "R801", "R802", "R807_A", "R807_B", "R807_C", "R808",
        "R809_D", "R810_A", "R810_D", cfg["ol_col"],
    ]
    if cfg["sector_col"]:
        ind_cols.append(cfg["sector_col"])
    if cfg["ict_col"]:
        ind_cols.append(cfg["ict_col"])

    df_ind = pd.read_csv(ind_path, usecols=ind_cols, dtype=str, keep_default_na=False)

    # Record full-wave population conservation baseline before filtering
    total_pop_weind = float(df_ind["FWT"].astype(float).sum())
    total_ind_sample = int(len(df_ind))

    # Extract Head of Household (KRT, R403 == '1') attributes
    df_krt = df_ind[df_ind["R403"].str.strip() == "1"][
        [hh_key, "R405", cfg["ijazah_col"]]
    ].copy()
    df_krt["krt_female"] = (df_krt["R405"].str.strip() == "2").astype(int)
    df_krt["krt_edu_cat"] = df_krt[cfg["ijazah_col"]].str.strip().map(lambda x: map_ijazah(x, year))
    df_krt = df_krt[[hh_key, "krt_female", "krt_edu_cat"]]

    # Build Household Context table (1:1 join RT + KP + KRT)
    df_hh = df_rt.merge(df_kp, on=hh_key, how="inner", validate="one_to_one")
    df_hh = df_hh.merge(df_krt, on=hh_key, how="inner", validate="one_to_one")

    r102_map = dict(zip(dim_wilayah["kode_r102"], dim_wilayah["kode_bps"]))
    df_hh["kode_r102"] = df_hh["R102"].str.strip().astype(int)
    df_hh["kode_bps"] = df_hh["kode_r102"].map(r102_map)
    df_hh["r105_urban"] = (df_hh["R105"].str.strip() == "1").astype(int)
    df_hh["tahun"] = year
    df_hh["hh_uid"] = f"{year}_" + df_hh[hh_key].str.strip()
    df_hh["psu_wi1"] = f"{year}_" + df_hh["WI1"].str.strip()
    df_hh["strata_code"] = df_hh["kode_r102"] * 10 + df_hh["R105"].str.strip().astype(int)
    df_hh["hh_size"] = df_hh["R301"].str.strip().astype(int)
    df_hh["wert"] = df_hh["WERT"].astype(float)
    df_hh["weind_hh_sum"] = df_hh["WEIND"].astype(float)
    df_hh["food"] = df_hh["FOOD"].astype(float)
    df_hh["nonfood"] = df_hh["NONFOOD"].astype(float)
    df_hh["expend"] = df_hh["EXPEND"].astype(float)
    df_hh["kapita"] = df_hh["KAPITA"].astype(float)
    df_hh["log_kapita"] = np.log(df_hh["kapita"])
    df_hh["exp_quintile"] = weighted_quintile(df_hh["kapita"].to_numpy(), df_hh["wert"].to_numpy())
    df_hh["rt_has_computer_r2001f"] = (df_hh["R2001F"].str.strip() == "1").astype(int)
    df_hh["has_pkh"] = (df_hh["R2204A"].str.strip() == "1").astype(int)
    df_hh["electric_light"] = df_hh["R1816"].str.strip().isin(["1", "2"]).astype(int)

    hh_keep = [
        "hh_uid", "tahun", "kode_bps", "r105_urban", "strata_code", "psu_wi1",
        "wert", "weind_hh_sum", "hh_size", "food", "nonfood", "expend",
        "kapita", "log_kapita", "exp_quintile", "krt_female", "krt_edu_cat",
        "rt_has_computer_r2001f", "has_pkh", "electric_light",
    ]
    df_hh_clean = df_hh[hh_keep].copy()

    # Filter Secondary Students (currently attending school == '2' & secondary codes)
    level_map = LEVEL_MAP_2020_2021 if year in (2020, 2021) else LEVEL_MAP_2022_2023
    att_mask = df_ind[cfg["attending_col"]].str.strip() == "2"
    lvl_clean = df_ind[cfg["level_col"]].str.strip()
    sec_mask = att_mask & lvl_clean.isin(level_map.keys())
    df_s = df_ind[sec_mask].copy()

    df_s["hh_uid"] = f"{year}_" + df_s[hh_key].str.strip()
    df_s["r401_str"] = df_s["R401"].str.strip()
    df_s["student_uid"] = df_s["hh_uid"] + "_" + df_s["r401_str"]
    df_s["weind"] = df_s["FWT"].astype(float)
    df_s["age"] = df_s["R407"].str.strip().astype(int)
    df_s["female"] = (df_s["R405"].str.strip() == "2").astype(int)

    lvl_tuples = df_s[cfg["level_col"]].str.strip().map(level_map)
    df_s["school_level"] = [t[0] for t in lvl_tuples]
    df_s["school_tier"] = [t[1] for t in lvl_tuples]
    df_s["is_formal_secondary"] = [t[2] for t in lvl_tuples]
    df_s["is_typical_age_11_19"] = ((df_s["age"] >= 11) & (df_s["age"] <= 19)).astype(int)

    if cfg["sector_col"]:
        sec_map = {"1": "Negeri", "2": "Swasta"}
        df_s["school_sector"] = df_s[cfg["sector_col"]].str.strip().map(sec_map)
    else:
        df_s["school_sector"] = None

    df_s["has_kip"] = df_s[cfg["kip_col"]].str.strip().isin(["1", "2"]).astype(int)
    df_s["has_pip"] = (df_s[cfg["pip_col"]].str.strip() == "1").astype(int)

    # ICT Outcomes & Devices
    df_s["online_learning"] = (df_s[cfg["ol_col"]].str.strip() == cfg["ol_marker"]).astype(int)
    if cfg["ict_col"]:
        ict_s = df_s[cfg["ict_col"]].str.strip()
        df_s["ict_literacy"] = np.where(ict_s == "1", 1, np.where(ict_s == "5", 0, np.nan))
    else:
        df_s["ict_literacy"] = np.nan

    df_s["uses_phone"] = (df_s["R801"].str.strip() == "1").astype(int)
    df_s["owns_phone"] = (df_s["R802"].str.strip() == "1").astype(int)
    df_s["uses_pc_desktop"] = (df_s["R807_A"].str.strip() == "A").astype(int)
    df_s["uses_laptop"] = (df_s["R807_B"].str.strip() == "B").astype(int)
    df_s["uses_tablet"] = (df_s["R807_C"].str.strip() == "C").astype(int)
    df_s["has_computer_device"] = (
        (df_s["uses_pc_desktop"] == 1)
        | (df_s["uses_laptop"] == 1)
        | (df_s["uses_tablet"] == 1)
    ).astype(int)
    df_s["device_tier"] = np.where(
        df_s["has_computer_device"] == 1,
        "PC_Laptop_Tablet",
        np.where((df_s["uses_phone"] == 1) | (df_s["owns_phone"] == 1), "HP_Only", "None"),
    )
    df_s["uses_internet"] = (df_s["R808"].str.strip() == "1").astype(int)
    df_s["internet_via_hp"] = (df_s["R809_D"].str.strip() == "D").astype(int)
    df_s["internet_at_home"] = (df_s["R810_A"].str.strip() == "A").astype(int)
    df_s["internet_at_school"] = (df_s["R810_D"].str.strip() == "D").astype(int)

    # Merge Household Context & Wilayah Metadata
    hh_cols_join = [
        "hh_uid", "tahun", "kode_bps", "r105_urban", "strata_code", "psu_wi1",
        "wert", "hh_size", "kapita", "log_kapita", "exp_quintile",
        "krt_female", "krt_edu_cat", "rt_has_computer_r2001f", "has_pkh",
    ]
    df_s = df_s.merge(df_hh_clean[hh_cols_join], on="hh_uid", how="inner", validate="many_to_one")
    df_s = df_s.merge(
        dim_wilayah[["kode_bps", "nama_wilayah_std", "tipe_wilayah"]],
        on="kode_bps",
        how="inner",
        validate="many_to_one",
    )

    # Wave-normalized & cluster-normalized & p99-trimmed weights
    df_s["weind_norm_wave"] = df_s["weind"] / df_s["weind"].mean()
    df_s["weind_norm_kab"] = df_s["weind"] / df_s.groupby("kode_bps")["weind"].transform("mean")
    p99 = float(np.quantile(df_s["weind"], 0.99))
    df_s["weind_trim_p99"] = np.minimum(df_s["weind"], p99)
    df_s["weind_trim_norm_wave"] = df_s["weind_trim_p99"] / df_s["weind_trim_p99"].mean()

    # Count secondary students per HH in this wave
    hh_counts = df_s.groupby("hh_uid")["student_uid"].transform("count")
    df_s["n_sec_students_in_hh"] = hh_counts.astype(int)
    df_s["in_track_a_formal"] = df_s["is_formal_secondary"].astype(int)
    df_s["in_track_b_formal"] = ((df_s["is_formal_secondary"] == 1) & (year in (2022, 2023))).astype(int)

    stu_keep = [
        "student_uid", "hh_uid", "tahun", "kode_bps", "nama_wilayah_std", "tipe_wilayah",
        "r105_urban", "strata_code", "psu_wi1", "weind", "weind_norm_wave",
        "weind_norm_kab", "weind_trim_p99", "weind_trim_norm_wave",
        "age", "female", "school_level", "school_tier", "is_formal_secondary",
        "is_typical_age_11_19", "school_sector", "online_learning", "ict_literacy",
        "uses_phone", "owns_phone", "uses_pc_desktop", "uses_laptop", "uses_tablet",
        "has_computer_device", "device_tier", "uses_internet", "internet_via_hp",
        "internet_at_home", "internet_at_school", "kapita", "log_kapita",
        "exp_quintile", "hh_size", "krt_female", "krt_edu_cat",
        "rt_has_computer_r2001f", "has_pkh", "has_kip", "has_pip",
        "n_sec_students_in_hh", "in_track_a_formal", "in_track_b_formal",
    ]
    df_s_clean = df_s[stu_keep].copy()

    wave_stats = {
        "tahun": year,
        "total_hh_sample": int(len(df_hh_clean)),
        "total_ind_sample": total_ind_sample,
        "total_pop_weind": total_pop_weind,
        "total_hh_wert": float(df_hh_clean["wert"].sum()),
        "n_sec_all": int(len(df_s_clean)),
        "n_sec_formal": int((df_s_clean["is_formal_secondary"] == 1).sum()),
        "weind_p99_threshold": p99,
    }
    return df_hh_clean, df_s_clean, wave_stats


def build_agg_summary(df_students: pd.DataFrame) -> pd.DataFrame:
    """Compute weighted regional prevalence & Kish effective N for formal secondary students."""
    formal = df_students[df_students["is_formal_secondary"] == 1].copy()
    rows = []
    for (yr, kb, nm, tp), g in formal.groupby(["tahun", "kode_bps", "nama_wilayah_std", "tipe_wilayah"]):
        w = g["weind"].to_numpy()
        ol_p, n_eff, ol_se = weighted_mean_and_se(g["online_learning"].to_numpy(), w)
        pc_p, _, _ = weighted_mean_and_se(g["has_computer_device"].to_numpy(), w)
        net_p, _, _ = weighted_mean_and_se(g["uses_internet"].to_numpy(), w)
        if g["ict_literacy"].notna().all():
            ict_p, _, ict_se = weighted_mean_and_se(g["ict_literacy"].to_numpy(), w)
            ict_pct = round(ict_p * 100.0, 2)
            ict_se_pct = round(ict_se * 100.0, 2)
        else:
            ict_pct = None
            ict_se_pct = None
        rows.append(
            {
                "tahun": int(yr),
                "kode_bps": str(kb),
                "nama_wilayah_std": str(nm),
                "tipe_wilayah": str(tp),
                "n_students_formal": int(len(g)),
                "weighted_pop_students": round(float(np.sum(w)), 1),
                "kish_n_eff": round(n_eff, 1),
                "deff_kish": round(float(len(g)) / max(1.0, n_eff), 3),
                "weighted_online_learning_pct": round(ol_p * 100.0, 2),
                "ol_se_pct": round(ol_se * 100.0, 2),
                "weighted_ict_literacy_pct": ict_pct,
                "ict_se_pct": ict_se_pct,
                "weighted_pc_laptop_pct": round(pc_p * 100.0, 2),
                "weighted_internet_pct": round(net_p * 100.0, 2),
            }
        )
    return pd.DataFrame(rows).sort_values(["tahun", "kode_bps"]).reset_index(drop=True)


def run_qa_checks(
    df_hh: pd.DataFrame,
    df_stu: pd.DataFrame,
    df_agg: pd.DataFrame,
    wave_stats: List[dict],
) -> Tuple[pd.DataFrame, dict]:
    """Execute 4-tier automated QA checks aligned with PRD Success Criteria."""
    logs = []

    def log(tier: str, sc: str, check_name: str, passed: bool, observed: str, threshold: str):
        logs.append(
            {
                "tier": tier,
                "success_criterion": sc,
                "check_name": check_name,
                "status": "PASS" if passed else "FAIL",
                "observed_value": observed,
                "threshold": threshold,
            }
        )

    # Tier 1: Pydantic Contract Validation on stratified sample + full agg table
    sample_records = df_stu.sample(min(2000, len(df_stu)), random_state=42).to_dict(orient="records")
    pyd_stu_errors = 0
    for rec in sample_records:
        if pd.isna(rec["ict_literacy"]):
            rec["ict_literacy"] = None
        else:
            rec["ict_literacy"] = int(rec["ict_literacy"])
        try:
            StudentRecordContract(**rec)
        except ValidationError:
            pyd_stu_errors += 1
    log("Tier 1", "SC-3", "Pydantic StudentRecordContract (2000 sample)", pyd_stu_errors == 0, f"errors={pyd_stu_errors}", "0 errors")

    pyd_agg_errors = 0
    for rec in df_agg.to_dict(orient="records"):
        try:
            WilayahWaveContract(**rec)
        except ValidationError:
            pyd_agg_errors += 1
    log("Tier 1", "SC-1", "Pydantic WilayahWaveContract (108 cells)", pyd_agg_errors == 0, f"errors={pyd_agg_errors}", "0 errors")

    # Tier 2: Relational, Key Uniqueness & Weight Conservation
    stu_uniq = df_stu["student_uid"].nunique() == len(df_stu)
    hh_uniq = df_hh["hh_uid"].nunique() == len(df_hh)
    orphans = len(set(df_stu["hh_uid"]) - set(df_hh["hh_uid"]))
    n_cells = len(df_agg)
    log("Tier 2", "SC-1", "Unique primary keys (student_uid & hh_uid)", stu_uniq and hh_uniq, f"stu_uniq={stu_uniq}, hh_uniq={hh_uniq}", "Both True")
    log("Tier 2", "SC-1", "Zero orphan students vs household context", orphans == 0, f"orphans={orphans}", "0")
    log("Tier 2", "SC-1", "Full 27 Kab/Kota x 4 Waves coverage", n_cells == 108, f"cells={n_cells}", "108")

    # Weight checks
    max_norm_dev = float(np.max(np.abs(df_stu.groupby("tahun")["weind_norm_wave"].mean() - 1.0)))
    min_weind = float(df_stu["weind"].min())
    min_kapita = float(df_stu["kapita"].min())
    log("Tier 2", "SC-2", "Positive weights & KAPITA, mean(weind_norm_wave)==1", (min_weind > 0 and min_kapita > 0 and max_norm_dev < 1e-6), f"min_w={min_weind:.2f}, max_dev={max_norm_dev:.2e}", ">0 and dev<1e-6")

    # Crosswalk checks (R812 NULL in 20-21, non-NULL in 22-23; KRT edu unknown == 0)
    ict_20_21_null = int(df_stu[df_stu["tahun"].isin([2020, 2021])]["ict_literacy"].isna().sum()) == int((df_stu["tahun"].isin([2020, 2021])).sum())
    ict_22_23_nonnull = int(df_stu[df_stu["tahun"].isin([2022, 2023])]["ict_literacy"].notna().sum()) == int((df_stu["tahun"].isin([2022, 2023])).sum())
    unknown_edu = int((df_stu["krt_edu_cat"] == "Unknown").sum())
    log("Tier 3", "SC-3", "R812 ICT Literacy strictly 2022-2023 only", ict_20_21_null and ict_22_23_nonnull, f"20-21_null={ict_20_21_null}, 22-23_ok={ict_22_23_nonnull}", "Both True")
    log("Tier 3", "SC-3", "KRT Education harmonization 0 Unknown", unknown_edu == 0, f"unknown={unknown_edu}", "0")

    # KIP vs PIP 2022 sanity check (check formal students)
    formal = df_stu[df_stu["is_formal_secondary"] == 1].copy()
    pip_by_yr = formal.groupby("tahun")["has_pip"].mean().to_dict()
    kip_by_yr = formal.groupby("tahun")["has_kip"].mean().to_dict()
    pip_sane = 0.05 <= pip_by_yr[2022] <= 0.25 and 0.05 <= kip_by_yr[2022] <= 0.25
    log("Tier 3", "SC-3", "KIP/PIP 2022 crosswalk plausibility", pip_sane, f"2022 PIP={pip_by_yr[2022]:.3f}, KIP={kip_by_yr[2022]:.3f}", "Between 0.05 and 0.25")

    # Tier 3: Empirical plausibility (2021 peak > 2020 & 2023; Urban > Rural; Q5 > Q1)
    ol_yr = {}
    for yr, g in formal.groupby("tahun"):
        p, _, _ = weighted_mean_and_se(g["online_learning"].to_numpy(), g["weind"].to_numpy())
        ol_yr[int(yr)] = p * 100.0
    inverted_u = (ol_yr[2021] > ol_yr[2020]) and (ol_yr[2021] > ol_yr[2023])
    p_urb, _, _ = weighted_mean_and_se(formal[formal["r105_urban"] == 1]["online_learning"].to_numpy(), formal[formal["r105_urban"] == 1]["weind"].to_numpy())
    p_rur, _, _ = weighted_mean_and_se(formal[formal["r105_urban"] == 0]["online_learning"].to_numpy(), formal[formal["r105_urban"] == 0]["weind"].to_numpy())
    p_q5, _, _ = weighted_mean_and_se(formal[formal["exp_quintile"] == 5]["online_learning"].to_numpy(), formal[formal["exp_quintile"] == 5]["weind"].to_numpy())
    p_q1, _, _ = weighted_mean_and_se(formal[formal["exp_quintile"] == 1]["online_learning"].to_numpy(), formal[formal["exp_quintile"] == 1]["weind"].to_numpy())

    log("Tier 3", "SC-5", "Pandemic inverted-U trajectory (2021 peak)", inverted_u, f"2020={ol_yr[2020]:.1f}%, 2021={ol_yr[2021]:.1f}%, 2022={ol_yr[2022]:.1f}%, 2023={ol_yr[2023]:.1f}%", "2021 > 2020 & 2023")
    log("Tier 3", "SC-5", "Digital divide direction (Urban>Rural & Q5>Q1)", (p_urb > p_rur) and (p_q5 > p_q1), f"Urb={p_urb*100:.1f}% vs Rur={p_rur*100:.1f}%; Q5={p_q5*100:.1f}% vs Q1={p_q1*100:.1f}%", "Urb>Rur and Q5>Q1")

    # Tier 4: Multilevel Readiness Diagnostics
    hh_stu_dist = formal.groupby("hh_uid")["student_uid"].count()
    pct_hh_multi = float((hh_stu_dist >= 2).mean() * 100.0)
    kab_sizes = formal.groupby("kode_bps")["student_uid"].count()
    min_kab_n = int(kab_sizes.min())
    _, n_eff_all, _ = weighted_mean_and_se(formal["online_learning"].to_numpy(), formal["weind"].to_numpy())
    deff_all = float(len(formal)) / n_eff_all
    log("Tier 4", "SC-4", "Kab/Kota cluster size >= 200 across 4 waves", min_kab_n >= 200, f"min_kab_n={min_kab_n}, median={int(kab_sizes.median())}, max={int(kab_sizes.max())}", ">=200")
    log("Tier 4", "SC-4", "Multi-student HH ratio & Kish DEFF audit", True, f"HH>=2_students={pct_hh_multi:.2f}%, Kish_DEFF={deff_all:.3f}", "Diagnostic logged")

    summary_diag = {
        "formal_n": int(len(formal)),
        "all_sec_n": int(len(df_stu)),
        "ol_by_year_pct": {k: round(v, 2) for k, v in ol_yr.items()},
        "urban_ol_pct": round(p_urb * 100.0, 2),
        "rural_ol_pct": round(p_rur * 100.0, 2),
        "q1_ol_pct": round(p_q1 * 100.0, 2),
        "q5_ol_pct": round(p_q5 * 100.0, 2),
        "pct_hh_multi_students": round(pct_hh_multi, 2),
        "kab_min_n": min_kab_n,
        "kab_median_n": int(kab_sizes.median()),
        "kab_max_n": int(kab_sizes.max()),
        "kish_deff": round(deff_all, 3),
        "kish_n_eff": round(n_eff_all, 1),
    }
    return pd.DataFrame(logs), summary_diag


def write_data_dictionary(out_path: Path, df_stu: pd.DataFrame, df_hh: pd.DataFrame) -> None:
    lines = [
        "# Data Dictionary: Master Database `J2-T1` (SUSENAS Jawa Barat 2020–2023)",
        "",
        f"- **Tabel Utama (`fact_secondary_students`):** `{len(df_stu):,}` baris (`{(df_stu['is_formal_secondary']==1).sum():,}` siswa formal + `{(df_stu['is_formal_secondary']==0).sum():,}` jalur non-formal/SLB).",
        f"- **Tabel Konteks (`fact_household_context`):** `{len(df_hh):,}` rumah tangga (`2020–2023`).",
        "",
        "## Kolom Inti `fact_secondary_students`",
        "",
        "| Kolom | Tipe | Definisi Operasional | Keterangan / Ketersediaan |",
        "| :--- | :--- | :--- | :--- |",
        "| `student_uid` | `string` | Primary key unik (`{tahun}_{hh_id}_{R401}`) | `2020–2023` |",
        "| `hh_uid` | `string` | Foreign key rumah tangga (`{tahun}_{RENUM/URUT}`) | `2020–2023` |",
        "| `tahun` | `int` | Gelombang survei SUSENAS Maret (`2020–2023`) | `2020–2023` |",
        "| `kode_bps` | `string` | Kode BPS 4-digit Kab/Kota (`3201–3279`) | `27` Kab/Kota |",
        "| `r105_urban` | `int` | `1` = Perkotaan, `0` = Perdesaan | `2020–2023` |",
        "| `strata_code` | `int` | `47` strata survei (`kode_r102 * 10 + R105`) | Direkonstruksi konsisten di `2023` |",
        "| `psu_wi1` | `string` | Primary Sampling Unit (`{tahun}_{WI1}`) | Konsisten 1:1 dgn `PSU` |",
        "| `weind` | `float` | Bobot ekspansi individu (`FWT` pada `KOR IND1`) | `> 0` |",
        "| `weind_norm_wave` | `float` | Bobot individu dinormalisasi (`mean = 1.0` per gelombang) | Untuk model multilevel |",
        "| `weind_norm_kab` | `float` | Bobot dinormalisasi di dalam klaster `(tahun, kode_bps)` | Skala bobot Carle (2009) |",
        "| `weind_trim_norm_wave` | `float` | Bobot ternormalisasi hasil winsorizing persentil 99 | Untuk uji sensitivitas |",
        "| `age` | `int` | Umur individu (`R407`) dalam tahun | `2020–2023` |",
        "| `female` | `int` | `1` = Perempuan, `0` = Laki-laki (`R405`) | `2020–2023` |",
        "| `school_level` | `string` | Jenjang (`SMP`, `MTs`, `SMA`, `MA`, `SMK`, `MAK`, `Paket B/C`, dll.) | Crosswalk `R613` (`20–21`) & `R612` (`22–23`) |",
        "| `school_tier` | `string` | `Junior_Secondary`, `Senior_General`, `Senior_Vocational` | `2020–2023` |",
        "| `is_formal_secondary` | `int` | `1` = SMP/MTs/SMA/MA/SMK/MAK, `0` = Paket/SLB/SPM | Flag sampel utama vs sensitivitas |",
        "| `is_typical_age_11_19` | `int` | `1` = Umur `11–19` tahun, `0` = di luar rentang | Filter usia remaja lazim |",
        "| `school_sector` | `string` | `Negeri` / `Swasta` (`R611`) | Tersedia `2022–2023` (`NULL` di `20–21`) |",
        "| `online_learning` | `int` | `1` = Pakai internet utk pembelajaran (`R811_B` `20–21` / `R811_H` `22–23`), `0` = Tidak | **Outcome Track A & B (`2020–2023`)** |",
        "| `ict_literacy` | `float/int` | `1` = Pernah belajar TIK (`R812=1`), `0` = Tidak (`R812=5`) | **Outcome Track B (`2022–2023` only)** |",
        "| `has_computer_device` | `int` | `1` = Memakai PC (`R807_A`), Laptop (`R807_B`), atau Tablet (`R807_C`) | `2020–2023` |",
        "| `device_tier` | `string` | `None`, `HP_Only`, `PC_Laptop_Tablet` | `2020–2023` |",
        "| `uses_internet` | `int` | `1` = Menggunakan internet dalam 3 bulan terakhir (`R808=1`) | `2020–2023` |",
        "| `internet_at_home` | `int` | `1` = Mengakses internet di rumah sendiri (`R810_A`) | `2020–2023` |",
        "| `internet_at_school` | `int` | `1` = Mengakses internet di sekolah/kampus (`R810_D`) | `2020–2023` |",
        "| `kapita`, `log_kapita`, `exp_quintile` | `float/int` | Pengeluaran per kapita RT (`KP 4.3`), log natural, & kuintil terboboti `1–5` | Kuintil dihitung atas seluruh RT per gelombang |",
        "| `krt_female`, `krt_edu_cat` | `int/string` | Gender & tingkat ijazah KRT (`No_Primary` s.d. `Tertiary_Univ`) | Harmonisasi `R615` (`20–21`) & `R614` (`22–23`) |",
        "| `has_kip`, `has_pip` | `int` | Penerima KIP (`1,2`) & PIP (`1`) | Koreksi swap `2022` sudah diterapkan |",
        "| `n_sec_students_in_hh` | `int` | Banyaknya siswa menengah pada `hh_uid` yang sama | Audit multilevel level-RT |",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_qa_report(
    out_path: Path,
    qa_df: pd.DataFrame,
    diag: dict,
    wave_stats: List[dict],
    df_stu: pd.DataFrame,
    elapsed_s: float,
) -> None:
    formal = df_stu[df_stu["is_formal_secondary"] == 1].copy()
    # Compute weighted summary Table 1 preview by year
    t1_rows = []
    for yr in WAVES:
        g = formal[formal["tahun"] == yr]
        w = g["weind"].to_numpy()
        p_ol, n_eff, _ = weighted_mean_and_se(g["online_learning"].to_numpy(), w)
        p_pc, _, _ = weighted_mean_and_se(g["has_computer_device"].to_numpy(), w)
        p_net, _, _ = weighted_mean_and_se(g["uses_internet"].to_numpy(), w)
        p_urb, _, _ = weighted_mean_and_se(g["r105_urban"].to_numpy(), w)
        p_ict = "-"
        if g["ict_literacy"].notna().all():
            v, _, _ = weighted_mean_and_se(g["ict_literacy"].to_numpy(), w)
            p_ict = f"{v*100:.2f}%"
        t1_rows.append(
            f"| {yr} | {len(g):,} | {np.sum(w):,.0f} | {n_eff:,.1f} | {p_urb*100:.1f}% | {p_net*100:.1f}% | {p_pc*100:.1f}% | **{p_ol*100:.2f}%** | **{p_ict}** |"
        )

    lines = [
        "# Laporan Audit Kualitas Data & Kesiapan Pemodelan (`J2-T1`)",
        "",
        f"- **Waktu Eksekusi Pipeline:** `{elapsed_s:.2f}` detik",
        f"- **Total Sampel Rumah Tangga (`fact_household_context`):** `{sum(x['total_hh_sample'] for x in wave_stats):,}` RT (`2020–2023`)",
        f"- **Total Siswa Menengah Semua Jalur (`fact_secondary_students`):** `{diag['all_sec_n']:,}` siswa",
        f"- **Total Siswa Menengah Formal (`in_track_a_formal = 1`):** `{diag['formal_n']:,}` siswa (`SMP/MTs/SMA/MA/SMK/MAK`)",
        "",
        "## 1. Hasil Evaluasi Otomatis (4-Tier PRD QA Gate)",
        "",
        "| Tier | Kriteria | Pemeriksaan | Status | Nilai Teramati | Ambang Batas |",
        "| :--- | :--- | :--- | :---: | :--- | :--- |",
    ]
    for _, r in qa_df.iterrows():
        lines.append(
            f"| {r['tier']} | {r['success_criterion']} | {r['check_name']} | **{r['status']}** | `{r['observed_value']}` | `{r['threshold']}` |"
        )

    lines.extend(
        [
            "",
            "## 2. Ringkasan Deskriptif Awal Siswa Menengah Formal (Terboboti `WEIND`)",
            "",
            "| Tahun | $n$ Sampel | Populasi Terboboti | Kish $N_{\\text{eff}}$ | Urban (%) | Internet (%) | PC/Laptop/Tablet (%) | Online Learning (%) | ICT Literacy (`R812`, %) |",
            "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
            *t1_rows,
            "",
            "## 3. Diagnostik Kesiapan Model Multilevel",
            "",
            f"- **Ukuran Klaster 27 Kab/Kota (gabungan 4 gelombang formal):** Min = `{diag['kab_min_n']}` siswa, Median = `{diag['kab_median_n']}` siswa, Maks = `{diag['kab_max_n']}` siswa.",
            f"- **Rasio Rumah Tangga dengan >= 2 Siswa Menengah:** `{diag['pct_hh_multi_students']:.2f}%` dari rumah tangga beranak sekolah menengah.",
            f"  - *Rekomendasi Statistik:* Karena sebagian besar RT hanya memiliki `1` siswa menengah (`{100 - diag['pct_hh_multi_students']:.2f}%`), model **2-Level (`Siswa -> 27 Kab/Kota x Gelombang` atau `Siswa -> Kab/Kota` dengan fixed effect gelombang dan cluster-robust SE di level PSU/RT)** lebih stabil daripada memaksakan random intercept RT 3-level yang rawan *singular fit*.",
            f"- **Design Effect Gabungan (Kish DEFF):** `{diag['kish_deff']:.3f}` (Effective Sample Size $N_{{\\text{{eff}}}} = {diag['kish_n_eff']:,.1f}$ dari $N = {diag['formal_n']:,}$).",
            f"- **Gradien Awal Ketimpangan Digital (`Online Learning` Terboboti 2020–2023):**",
            f"  - Kota (`{diag['urban_ol_pct']:.2f}%`) vs Desa (`{diag['rural_ol_pct']:.2f}%`)",
            f"  - Kuintil 5 Terkaya (`{diag['q5_ol_pct']:.2f}%`) vs Kuintil 1 Termiskin (`{diag['q1_ol_pct']:.2f}%`)",
        ]
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    t0 = time.perf_counter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dim_wilayah = load_dim_wilayah()
    dim_gelombang = pd.DataFrame(
        [
            {"tahun": 2020, "fase_pandemi": "Awal Pandemi (Maret 2020)", "join_key_asal": "RENUM", "catatan_kuesioner": "Online learning di R811_B; status sekolah R612; belum ada R812 & R611"},
            {"tahun": 2021, "fase_pandemi": "Puncak PJJ (Maret 2021)", "join_key_asal": "RENUM", "catatan_kuesioner": "Online learning di R811_B; status sekolah R612; belum ada R812 & R611"},
            {"tahun": 2022, "fase_pandemi": "Transisi Hybrid (Maret 2022)", "join_key_asal": "URUT", "catatan_kuesioner": "Online learning di R811_H; R812 & R611 mulai ada; R615=subsidi kuota, KIP=R616, PIP=R617"},
            {"tahun": 2023, "fase_pandemi": "Pasca-Pandemi (Maret 2023)", "join_key_asal": "URUT", "catatan_kuesioner": "Online learning di R811_H; R812 & R611 ada; STRATA direkonstruksi via R102xR105"},
        ]
    )

    hh_parts, stu_parts, wave_stats = [], [], []
    for yr in WAVES:
        hh_yr, stu_yr, st = process_wave(yr, dim_wilayah)
        hh_parts.append(hh_yr)
        stu_parts.append(stu_yr)
        wave_stats.append(st)

    df_hh = pd.concat(hh_parts, ignore_index=True)
    df_stu = pd.concat(stu_parts, ignore_index=True)
    df_agg = build_agg_summary(df_stu)

    qa_df, diag = run_qa_checks(df_hh, df_stu, df_agg, wave_stats)

    # Save Clean Flat Analytical Marts (CSV/CSV.GZ + optional Parquet fallback)
    df_hh.to_csv(OUT_DIR / "fact_household_context.csv.gz", index=False, compression="gzip")
    df_stu.to_csv(OUT_DIR / "fact_secondary_students.csv", index=False)
    df_agg.to_csv(OUT_DIR / "agg_kabkota_wave_summary.csv", index=False)
    parquet_exported = False
    try:
        df_hh.to_parquet(OUT_DIR / "fact_household_context.parquet", index=False)
        df_stu.to_parquet(OUT_DIR / "fact_secondary_students.parquet", index=False)
        df_agg.to_parquet(OUT_DIR / "agg_kabkota_wave_summary.parquet", index=False)
        parquet_exported = True
    except Exception as exc:
        print(f"Note: Parquet export skipped due to environment policy ({type(exc).__name__}); SQLite + CSV/CSV.GZ exported.")

    # Save Relational SQLite Master DB
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()
    with sqlite3.connect(SQLITE_PATH) as conn:
        dim_wilayah.to_sql("dim_wilayah", conn, index=False)
        dim_gelombang.to_sql("dim_gelombang", conn, index=False)
        df_hh.to_sql("fact_household_context", conn, index=False)
        df_stu.to_sql("fact_secondary_students", conn, index=False)
        df_agg.to_sql("agg_kabkota_wave_summary", conn, index=False)
        qa_df.to_sql("qa_audit_log", conn, index=False)

        conn.execute("CREATE INDEX idx_stu_tahun_kab ON fact_secondary_students(tahun, kode_bps)")
        conn.execute("CREATE INDEX idx_stu_hh ON fact_secondary_students(hh_uid)")
        conn.execute("CREATE INDEX idx_hh_tahun_kab ON fact_household_context(tahun, kode_bps)")
        conn.commit()

    elapsed = time.perf_counter() - t0
    # Note: Unified column dictionary, glossary, and formulas live in data/README.md + CODEBOOK.csv.
    write_qa_report(OUT_DIR / "qa_audit_report.md", qa_df, diag, wave_stats, df_stu, elapsed)

    print(f"BUILD COMPLETE in {elapsed:.2f}s")
    print(f"SQLite: {SQLITE_PATH}")
    print(f"QA Summary: {(qa_df['status'] == 'PASS').sum()}/{len(qa_df)} checks PASSED")
    print("Diag summary:", json.dumps(diag, indent=2))


if __name__ == "__main__":
    main()
