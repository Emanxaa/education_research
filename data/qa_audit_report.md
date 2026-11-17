# Laporan Audit Kualitas Data & Kesiapan Pemodelan (`J2-T1`)

- **Waktu Eksekusi Pipeline:** `11.44` detik
- **Total Sampel Rumah Tangga (`fact_household_context`):** `102,538` RT (`2020–2023`)
- **Total Siswa Menengah Semua Jalur (`fact_secondary_students`):** `29,802` siswa
- **Total Siswa Menengah Formal (`in_track_a_formal = 1`):** `28,556` siswa (`SMP/MTs/SMA/MA/SMK/MAK`)

## 1. Hasil Evaluasi Otomatis (4-Tier PRD QA Gate)

| Tier | Kriteria | Pemeriksaan | Status | Nilai Teramati | Ambang Batas |
| :--- | :--- | :--- | :---: | :--- | :--- |
| Tier 1 | SC-3 | Pydantic StudentRecordContract (2000 sample) | **PASS** | `errors=0` | `0 errors` |
| Tier 1 | SC-1 | Pydantic WilayahWaveContract (108 cells) | **PASS** | `errors=0` | `0 errors` |
| Tier 2 | SC-1 | Unique primary keys (student_uid & hh_uid) | **PASS** | `stu_uniq=True, hh_uniq=True` | `Both True` |
| Tier 2 | SC-1 | Zero orphan students vs household context | **PASS** | `orphans=0` | `0` |
| Tier 2 | SC-1 | Full 27 Kab/Kota x 4 Waves coverage | **PASS** | `cells=108` | `108` |
| Tier 2 | SC-2 | Positive weights & KAPITA, mean(weind_norm_wave)==1 | **PASS** | `min_w=1.31, max_dev=2.22e-16` | `>0 and dev<1e-6` |
| Tier 3 | SC-3 | R812 ICT Literacy strictly 2022-2023 only | **PASS** | `20-21_null=True, 22-23_ok=True` | `Both True` |
| Tier 3 | SC-3 | KRT Education harmonization 0 Unknown | **PASS** | `unknown=0` | `0` |
| Tier 3 | SC-3 | KIP/PIP 2022 crosswalk plausibility | **PASS** | `2022 PIP=0.147, KIP=0.176` | `Between 0.05 and 0.25` |
| Tier 3 | SC-5 | Pandemic inverted-U trajectory (2021 peak) | **PASS** | `2020=55.5%, 2021=81.0%, 2022=66.0%, 2023=34.8%` | `2021 > 2020 & 2023` |
| Tier 3 | SC-5 | Digital divide direction (Urban>Rural & Q5>Q1) | **PASS** | `Urb=60.7% vs Rur=53.1%; Q5=68.8% vs Q1=50.7%` | `Urb>Rur and Q5>Q1` |
| Tier 4 | SC-4 | Kab/Kota cluster size >= 200 across 4 waves | **PASS** | `min_kab_n=585, median=995, max=1512` | `>=200` |
| Tier 4 | SC-4 | Multi-student HH ratio & Kish DEFF audit | **PASS** | `HH>=2_students=9.80%, Kish_DEFF=1.660` | `Diagnostic logged` |

## 2. Ringkasan Deskriptif Awal Siswa Menengah Formal (Terboboti `WEIND`)

| Tahun | $n$ Sampel | Populasi Terboboti | Kish $N_{\text{eff}}$ | Urban (%) | Internet (%) | PC/Laptop/Tablet (%) | Online Learning (%) | ICT Literacy (`R812`, %) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 2020 | 7,410 | 3,960,367 | 4,705.3 | 77.8% | 88.2% | 38.5% | **55.46%** | **-** |
| 2021 | 7,083 | 4,011,053 | 4,547.4 | 79.4% | 95.1% | 22.2% | **81.05%** | **-** |
| 2022 | 6,982 | 4,001,461 | 4,367.8 | 80.2% | 95.2% | 28.1% | **66.04%** | **51.84%** |
| 2023 | 7,081 | 4,144,738 | 3,761.6 | 81.9% | 92.6% | 30.0% | **34.80%** | **42.69%** |

## 3. Diagnostik Kesiapan Model Multilevel

- **Ukuran Klaster 27 Kab/Kota (gabungan 4 gelombang formal):** Min = `585` siswa, Median = `995` siswa, Maks = `1512` siswa.
- **Rasio Rumah Tangga dengan >= 2 Siswa Menengah:** `9.80%` dari rumah tangga beranak sekolah menengah.
  - *Rekomendasi Statistik:* Karena sebagian besar RT hanya memiliki `1` siswa menengah (`90.20%`), model **2-Level (`Siswa -> 27 Kab/Kota x Gelombang` atau `Siswa -> Kab/Kota` dengan fixed effect gelombang dan cluster-robust SE di level PSU/RT)** lebih stabil daripada memaksakan random intercept RT 3-level yang rawan *singular fit*.
- **Design Effect Gabungan (Kish DEFF):** `1.660` (Effective Sample Size $N_{\text{eff}} = 17,199.2$ dari $N = 28,556$).
- **Gradien Awal Ketimpangan Digital (`Online Learning` Terboboti 2020–2023):**
  - Kota (`60.67%`) vs Desa (`53.07%`)
  - Kuintil 5 Terkaya (`68.80%`) vs Kuintil 1 Termiskin (`50.67%`)