# `J2-T1`: *The Post-Pandemic Digital Learning Divide* (`education_research`)

Repositori penelitian dan pipeline rekayasa data untuk naskah target ***Informatics in Education*** (*Scopus Q1 Education / Q2 CS, Diamond Open Access Rp 0*):

> *"The Post-Pandemic Digital Learning Divide: Multilevel Determinants of Online Learning Participation and ICT Literacy Among Secondary Students in West Java"*

---

## Navigasi Repositori

| Jalur | Deskripsi |
| :--- | :--- |
| **[`data/README.md`](data/README.md)** | **Panduan Navigasi Utama:** Kamus istilah, arsitektur relasional 6 tabel, definisi operasional & rumus lengkap (`96` kolom), aturan *crosswalk* `2020–2023`, dan quickstart SQL/Python/R. |
| [`data/CODEBOOK.csv`](data/CODEBOOK.csv) | Kamus skema kolom *machine-readable* (`96` entri pada `6` tabel). |
| [`data/agg_kabkota_wave_summary.csv`](data/agg_kabkota_wave_summary.csv) | Tabel agregat makro `27` Kab/Kota $\times$ `4` gelombang (`108` baris; persentase terboboti & Kish $N_{\text{eff}}$). |
| [`data/qa_audit_report.md`](data/qa_audit_report.md) | Laporan otomatis 13 uji kualitas data (`13/13 PASS`). |
| [`data/manifest.json`](data/manifest.json) & [`data/checksums_sha256.txt`](data/checksums_sha256.txt) | Metadata standar FAIR & daftar *hash* `SHA-256` seluruh artefak `data/`. |
| [`data/examples/`](data/examples/quickstart_explore.py) | Skrip contoh [`quickstart_explore.py`](data/examples/quickstart_explore.py) & [`quickstart_multilevel.R`](data/examples/quickstart_multilevel.R) (`survey::svydesign` + `lme4::glmer`). |
| [`build_master_db.py`](build_master_db.py) | Skrip ETL *lazy-loading* (*column-projected*) dari mikrodata mentah SUSENAS `2020–2023` + validasi kontrak Pydantic v2. |
| [`verify_master_db.py`](verify_master_db.py) | Suite verifikasi independen pasca-build (paritas SQLite vs CSV, integritas FK, ringkasan Track A & B). |

---

## Kebijakan Berkas Mikrodata (`.gitignore`)

Sesuai etika diseminasi mikrodata survei **Badan Pusat Statistik (BPS RI)**, berkas mikrodata tingkat siswa dan rumah tangga **tidak diunggah** ke repositori GitHub publik ini dan otomatis diabaikan oleh [`.gitignore`](.gitignore):

- `data/master_j2_t1_digital_learning.sqlite`
- `data/fact_secondary_students.csv`
- `data/fact_household_context.csv.gz`

Pemegang akses resmi mikrodata **SUSENAS Maret `2020–2023` Provinsi Jawa Barat (BPS RI)** dapat membangun ulang seluruh berkas lokal secara deterministik dan memvalidasi keutuhan *checksum*-nya dengan:

```bash
python build_master_db.py
python verify_master_db.py
python data/examples/quickstart_explore.py
```

Jika Anda sudah menerima bundel data bersih secara terpisah dari peneliti, salin ke folder `data/` lalu langsung baca **[`data/README.md`](data/README.md)** untuk panduan navigasi, kamus istilah, dan rumus tiap variabel.
