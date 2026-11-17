# ==============================================================================
# Quickstart R Script: J2-T1 Multilevel Survey Modeling Template
# Data: master_j2_t1_digital_learning.sqlite (SUSENAS Jawa Barat 2020-2023)
# ==============================================================================
# Paket yang dibutuhkan:
# install.packages(c("DBI", "RSQLite", "dplyr", "survey", "lme4", "performance"))

library(DBI)
library(RSQLite)
library(dplyr)
library(survey)
library(lme4)
library(performance)

# Sesuaikan path jika dijalankan dari direktori root data/
db_path <- if (file.exists("master_j2_t1_digital_learning.sqlite")) {
  "master_j2_t1_digital_learning.sqlite"
} else {
  "../master_j2_t1_digital_learning.sqlite"
}

con <- dbConnect(RSQLite::SQLite(), db_path)

# 1. Muat Track A (2020-2023, Formal) & Track B (2022-2023, Formal)
df_a <- dbGetQuery(con, "SELECT * FROM fact_secondary_students WHERE in_track_a_formal = 1") %>%
  mutate(
    tahun_f     = factor(tahun, levels = c(2020, 2021, 2022, 2023)),
    kode_bps    = factor(kode_bps),
    school_tier = factor(school_tier, levels = c("Junior_Secondary", "Senior_General", "Senior_Vocational")),
    device_tier = factor(device_tier, levels = c("None", "HP_Only", "PC_Laptop_Tablet")),
    exp_quint_f = factor(exp_quintile),
    krt_edu_cat = factor(krt_edu_cat, levels = c("No_Primary", "Primary_SD", "Junior_SMP", "Senior_SMA_SMK", "Tertiary_Univ"))
  )

df_b <- df_a %>%
  filter(in_track_b_formal == 1) %>%
  mutate(
    tahun_f       = factor(tahun, levels = c(2022, 2023)),
    school_sector = factor(school_sector, levels = c("Negeri", "Swasta"))
  )

dbDisconnect(con)

# 2. Estimasi Deskriptif Berbasis Desain Survei Kompleks (survey package)
options(survey.lonely.psu = "adjust")
des_a <- svydesign(ids = ~psu_wi1, strata = ~strata_code, weights = ~weind, data = df_a, nest = TRUE)
print(svyby(~online_learning, ~tahun_f + r105_urban, des_a, svymean, vartype = c("se", "ci")))

# 3. Model Multilevel 2-Level (Siswa -> 27 Kab/Kota) Track A
# Catatan: Gunakan weind_norm_kab (Carle 2009) atau weind_norm_wave sebagai bobot level-1;
# bandingkan estimasi unweighted vs weighted (disarankan juga glmmTMB / WeMix untuk level-1 scaled weights).
m0_null <- glmer(
  online_learning ~ 1 + (1 | kode_bps),
  data = df_a, family = binomial(link = "logit")
)
print(performance::icc(m0_null))

m4_full <- glmer(
  online_learning ~ age + female + school_tier + device_tier + internet_at_home +
    internet_at_school + exp_quint_f + krt_edu_cat + has_pip +
    r105_urban + tahun_f + exp_quint_f:r105_urban + exp_quint_f:tahun_f +
    (1 | kode_bps),
  data = df_a,
  family = binomial(link = "logit"),
  weights = weind_norm_kab,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)
summary(m4_full)
