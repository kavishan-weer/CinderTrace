# EMBERLINE: End-to-End Scientific, Data, Visualization & Analytics Audit

This review audits every layer of the current project—raw satellite archives, coverage/availability rules, harmonization math, uncertainty intervals, sub-regional allocation, frontend charts, and user-facing insights—against the actual Parquet and JSON datasets in your repository.

---

## Executive Summary: Where Accuracy Stands Today

| Layer | Accuracy Verdict | Key Finding from Data Audit |
|---|---|---|
| **Raw Archive Integrity** | ✅ **High** (with 1 critical gap) | Zero duplicate rows in LK/CA (2 in NSW out of 3.67M); zero SP/NRT same-day double-counting; 100% raw detection conservation into H3 cells. **Gap:** Multi-day satellite outages (57 S-NPP outage days since 2018; 17 Terra outage days in June 2001) are not flagged or gap-filled. |
| **Coverage & Missingness Rules** | 🔴 **Needs Fix** | `coverage.py` treats `0 detections in regional bbox` as `'missing'`. In Sri Lanka, this misclassifies **15 true-zero monsoon months** as missing sensor data, wiping out **8 of 11 pre-2012 years** as "incomplete" and biasing Nov/Dec/Jan medians upward. |
| **Regional Harmonization (2012–2025)** | ✅ **Strong & Verified** | Independent **nested LOYO** (`data/validation_nested/`) confirms real skill over naive scaling in all 9 slices. For the default `Vegetation · Nominal + High` view, monthly nested WAPE is **18.4% (LK), 11.8% (CA), 9.7% (NSW)**, and annual WAPE is **7.7% (LK), 5.7% (CA), 4.5% (NSW)** with Spearman $\rho = 0.91\text{–}0.94$. |
| **Terra-Only Era (2000–2002)** | 🟠 **Needs Wider Bands** | Two-stage `Terra → MODIS → S-NPP` scaling multiplies morning Terra counts by up to $49.4\times$ in Sri Lanka (`2001-03`). Held-out testing shows WAPE nearly doubles (**32.4% LK, 21.5% CA, 32.8% NSW**) and 80%-interval coverage drops to **58%–62%** because stage-1 variance is omitted. |
| **District / Custom AOI Allocation** | 🔴 **Needs Fix** | Compounding `loglog` non-zero intercepts at $M=0$ with `unallocatable_no_modis` and `sumKnown()` wipes out **34 of 135 pre-2012 months (and 11 of 11 pre-2012 years!)** in every Sri Lankan district under default filters. District WAPE is **34%–39%** in major fire districts but **>100%** in low-fire districts. |
| **Visualizations (Calendar, Map, Seam)** | 🔴 **Needs Fix** | Calendar `Anomaly`/`Percentile` modes blank out **60 eligible months (2000–2005)** due to a `r.month < month` filter and use a sequential color scale. `FireMap` normalizes height/color to each single month's max (making 1 cell-day look identical to 60+ cell-days). |
| **Current Insights (`SeasonInsights`)** | 🟠 **Low Utility as Built** | Because Theil–Sen slopes are computed on integer month indices ($0..11$), **all 24 trend cards across all 3 regions and both eras output `"No directional shift" (0.0 mo/dec)` or `"Insufficient evidence"`**. NSW peaks in **April** in 16/25 years due to autumn agricultural/hazard-reduction burning. |

---

## Part 1: Data & Pipeline Accuracy Bugs (Must Fix)

### 1.1 Unhandled Satellite Outages Corrupting Reference Months (`Critical`)
- **Evidence from `data/raw/`:**
  - Across all 3 regions combined, **Suomi-NPP had 57 days since 2018 with 0 detections** while NOAA-20 VIIRS was actively recording $\ge 20$ detections/day:
    - **`2022-08`: 10 missing days** (`2022-07-26` to `2022-08-11`, S-NPP spacecraft safe-mode anomaly, plus 5 days in `2022-07`).
    - **`2024-07`: 10 missing days** (`2024-07-09` to `2024-07-16` plus single-day gaps).
    - **`2026-07`: 5 missing days** (`2026-07-10` to `2026-07-16`).
    - **`2026-10` / `2026-11`:** In Sri Lanka, Aqua stops `2026-10-18` and S-NPP stops `2026-10-23`, while NOAA-20/21 continue to `2026-11-04`.
  - In the Terra-only era, **Terra was completely offline for 17 days from `2001-06-15` to `2001-07-02`** and **9 days from `2002-03-19` to `2002-03-29`**.
- **Impact on Data & Charts:**
  - Because `coverage.py` marks any month with $\ge 1$ detection as `'inferred_available'`, `2024-07` and `2022-08` are treated as 100% complete reference months.
  - In **California in July 2024 (`2024-07`, during the Park Fire outbreak)**, harmonized activity (`snpp = 507` cell-days) is **lower than raw coarse MODIS (`587`) and 43% lower than NOAA-20 (`897`)**!
  - In **August 2022 (`2022-08`)**, harmonized S-NPP undercounts activity by **42% in CA** (`311` vs `539` NOAA-20) and **36% in NSW** (`590` vs `915` NOAA-20), and corrupts LOYO training/validation.
- **Concrete Fix:**
  - Use **NOAA-20 VIIRS to gap-fill Suomi-NPP on verified S-NPP spacecraft outage days** (matching `winning_strategy.md` §3: *"VIIRS reference = Suomi-NPP. NOAA-20/21 are used only for gap-filling and validation, never stacked"*), and mark `2001-06` and `2002-03` (Terra-only multi-week outages) as `'provisional'` (`comparison_eligible = False`).

### 1.2 The "Zero Detections = Missing Sensor" Bug in `coverage.py` (`Critical`)
- **Evidence from `data/harmonized/lk_coverage.parquet`:**
  - `coverage.py` sets `state = 'missing'` whenever `n == 0` in a single region's bounding box.
  - In Sri Lanka, MODIS was operating normally (confirmed by thousands of detections in CA and NSW) but recorded `0` fire detections during **15 wet-monsoon months** (`2001-01, 2001-12, 2002-12, 2003-01, 2004-11, 2005-11, 2009-11, 2010-11, 2011-12` pre-VIIRS; `2012-11, 2012-12, 2015-11, 2015-12, 2023-12, 2025-01` in the overlap era).
- **Impact on Data & Charts:**
  1. **Wipes out 8 of 11 pre-VIIRS years in Sri Lanka:** Because 1 month (Nov, Dec, or Jan) is set to `NaN`, `SeasonInsights` rejects **2001, 2002, 2003, 2004, 2005, 2009, 2010, and 2011** as `"Incomplete · 11/12"`.
  2. **Biases Nov/Dec/Jan historical medians upward:** Excluding all zero-fire monsoon years from the pre-2012 baseline inflates the historical median and distorts percentiles for Nov, Dec, and Jan.
  3. **Excludes $M=0, V>0$ months from overlap training:** All 6 overlap months where MODIS saw 0 fires and S-NPP saw 2–12 cell-days are excluded from `training_ok`.
  4. **Breaks October 2026 in Region Comparison:** Because Sri Lanka had 0 S-NPP detections in early November 2026, `last_detection` falls in October 2026 (`2026-10-23`), marking `2026-10` as `'provisional'` in LK while CA and NSW mark `2026-10` as `'inferred_available'`.
- **Concrete Fix:**
  - Determine sensor operational status across **all regions combined** (plus known mission start/outage dates). When a sensor is active globally and has `0` detections in Sri Lanka during the monsoon, its regional count is a **valid `0.0`**, not `'missing'`.

### 1.3 Pre-2012 District & Custom-AOI Wipeout in Sri Lanka (`Critical`)
- **Evidence from `data/harmonized/lk_sub_monthly.parquet`:**
  - Under the default `Vegetation · Nominal + High` (`confs = [2, 3]`) filter, **0 out of 11 pre-2012 calendar years (`2001–2011`) are complete in any of Sri Lanka's 25 districts** (`34` of `135` pre-2012 months are `NaN`).
  - **Root cause:** In 25 pre-2012 months, regional $M_{\text{conf=2}} > 0$ but $M_{\text{conf=3}} = 0$. Because `veg/conf3` uses `loglog` ($\hat{V} = \exp(a_m + b\log(M+1)) - 1$), when $M_{\text{conf=3}} = 0$ the positive intercept still predicts $\hat{V}_{\text{conf=3}} \in [0.01, 0.61]$. Then `pipeline/analytics.py` (`selected_monthly`) sees `denom == 0` with `harmonized > 0`, marks `veg/conf3` as `unallocatable_no_modis` (`NaN`), and `sumKnown()` in `web/src/analytics.ts` (`values.every(v => v !== null)`) **nullifies the entire `Nominal + High` sum**, throwing away the valid `Nominal` (`conf=2`) estimate!
- **Concrete Fix:**
  1. Constrain transfer models so $M = 0 \implies \hat{V} = 0$ (or when allocating `conf=3` to sub-areas on a month with $M_{\text{conf=3}}=0$ and $M_{\text{conf=2}}>0$, allocate by `Nominal + High` MODIS share).
  2. Surface the district-level validation findings (`data/transfer_sensitivity_v1/report.json`): in Sri Lanka's major fire districts (Anuradhapura, Monaragala, Ampara), `conf=2` WAPE is **33.8%–38.8%**, whereas in low-fire districts (<50 cell-days/decade like Colombo or Jaffna) relative WAPE exceeds **100%**. Flag low-activity sub-regions in the UI when historical MODIS support is sparse.

### 1.4 Omitted Category/Confidence Slices Breaking Sidebar Filters & `RegionComparison` (`Major`)
- **Evidence from `*_monthly.parquet` and `web/src/comparison.ts`:**
  - `harmonize.py` skips any slice with `<10` total cell-days (`if d.modis.sum() + d.snpp.sum() < 10: continue`).
  - Consequently:
    - **`Volcanic` (`volcano`) has 0 slices in all 3 regions** (0 cells meet the volcanic threshold in LK, CA, or NSW).
    - **`Offshore` has 0 slices in NSW**, no `conf=3` in LK, and no `conf=1` in CA.
    - **`Industrial` (`static`) has no `conf=1` or `conf=3` in LK**.
  - In `web/src/comparison.ts` (`normalizedMonth`), `if (slices.length !== cats.length * confs.length) return {status: 'unsupported_slices'}`. Thus, under default `Nominal + High` confidence, checking **`Industrial`** breaks Sri Lanka in `RegionComparison`, checking **`Offshore`** breaks LK and NSW, and checking **`Volcanic`** breaks all 3 regions!
- **Concrete Fix:**
  - Emit zero-filled rows (`harmonized = 0`, `low_data = False`) for valid category/confidence combinations that simply had 0 detections, and either remove `Volcanic` from the LK/CA/NSW filter list or show `"0 volcanic sources in region"` instead of an error state.

### 1.5 Two-Stage Terra-Only (`2000-11` to `2002-07`) Transfer Error & Narrow Bands (`Major`)
- **Evidence:**
  - For `2000-11` through `2002-07`, `harmonize.py` scales morning Terra (10:30 AM) to `Terra + Aqua` using 2003–2011 monthly ratios (in Sri Lanka, $6.15\times$ in Feb and $5.35\times$ in Mar because agricultural fires occur in the afternoon) before applying the `MODIS → S-NPP` model.
  - Evaluating this two-stage `Terra → MODIS → S-NPP` chain on held-out overlap years shows WAPE jumps from **18.5% → 32.4% (LK)**, **13.4% → 21.5% (CA)**, and **14.7% → 32.8% (NSW)** with a **+7% to +11% positive bias**, while empirical coverage of the 80% interval drops to **58%–62%** because `lo`/`hi` only use stage-2 residuals.
- **Concrete Fix:**
  - Compute `lo`/`hi` for `2000-11` to `2002-07` from the end-to-end `Terra → S-NPP` LOYO residuals (so the 80% band reflects true two-stage uncertainty) and annotate the pre-Aqua boundary (`Aug 2002`) on timeline charts.

---

## Part 2: Visualization & Frontend Math Flaws (Must Fix)

### 2.1 Burning Calendar `Anomaly` & `Percentile` Modes Blank Out 2000–2005 & Use a Moving Baseline (`Critical`)
- **Evidence (`web/src/analytics.ts` line 12 & `web/src/Calendar.tsx` line 5):**
  - `historical()` filters `r.month < month` (strictly *prior* years only) and requires `values.length >= 5`.
  - When a user switches the Burning Calendar to **`Anomaly`** or **`Percentile`**:
    1. **60 eligible months (all of 2000–2005, and up to 2008 in Sri Lanka) turn completely grey (`"No comparison"`)**!
    2. **Every row of the calendar is benchmarked against a different climatology:** `2006` is compared only against `2001–2005` ($n=5$), whereas `2025` is compared against `2001–2024` ($n=24$).
    3. **Sequential Color Scale & 2× Clipping on Anomalies:** `Anomaly` mode maps `Math.min(2, d.value / h.median)` onto the same green-to-yellow sequential ramp (`color()`) as `Activity` mode. A month at $0.2\times$ normal, $1.0\times$ normal, and $5.0\times$ normal cannot be distinguished properly, and everything above $2\times$ median is clipped to the exact same color.
- **Concrete Fix:**
  1. In retrospective calendar views (`Calendar.tsx`, `SituationBrief.tsx`, `StatsStrip`), compute historical medians and percentiles against the **complete eligible multi-year climatology** (all eligible years in the record for that calendar month, or leave-one-year-out across all eligible years so every year 2000–2026 has $n \approx 24\text{–}25$ reference years and **0 blanked-out rows**).
  2. Use a **diverging, colorblind-safe ramp centered at $1.0\times$ median** (using $\log_2(\text{value}/\text{median})$ across e.g. $0.25\times \leftrightarrow 1.0\times \leftrightarrow 4.0\times+$) for `Anomaly` mode.

### 2.2 Map (`FireMap.tsx`) Auto-Scales Every Month to 100% Height & Brightness (`Major`)
- **Evidence (`web/src/FireMap.tsx` line 31):**
  - `const max = Math.max(1, ...data.map(d => d.value));`
  - Both 3D extrusion height (`d.value / max * 22000`) and fill color (`Math.sqrt(d.value / max)`) divide by that single month's `max`.
  - **Impact:** In a quiet month where the highest H3 cell in the region had `1` fire-active cell-day (`max = 1`), that single cell is extruded to **22 km maximum height and brightest HIGH color**—looking visually identical to a catastrophic megafire month where `max = 60`!
  - Furthermore, stepping from `2012-01` to `2012-02` switches the map layer from uncalibrated raw MODIS (`fam = 0`) to raw S-NPP (`fam = 1`), creating an artificial visual jump on the map.
- **Concrete Fix:**
  - Scale map colors and 3D heights against a **fixed physical ceiling** (e.g., $\log(1 + \text{cell\_days})$ up to $31\text{ cell-days/month}$, or the regional 99th percentile) and show numeric units on the map legend (`1` to `30+ cell-days`).

### 2.3 Seam Test (`SeamTest.tsx`) Ignores NSW Fire Year, Plots 1-Month Year 2000, and Hides Held-Out Overlap (`Major`)
- **Evidence (`web/src/SeamTest.tsx` line 6 & `web/src/App.tsx` line 22):**
  1. **Splits NSW Fire Seasons:** `SeamTest.tsx` groups by calendar year (`r.month.slice(0, 4)`), ignoring the July–June fire year used everywhere else for NSW. This splits NSW's 2019/20 Black Summer across two calendar years and computes the 2012/2011 ratio across split seasons.
  2. **Plots Year 2000 (1 Month) as an Annual Total:** Year `2000` only has December 2000 (`1/12` months), creating a fake near-zero drop at the start of the annual chart.
  3. **Shows Identity (`y = y`) Instead of Held-Out Predictions in 2012–2025:** In `Harmonized` mode, 2012–2025 is simply observed S-NPP (`viirs_observed`). Plotting the **held-out nested LOYO predictions (`data/validation_nested/predictions.parquet`) alongside observed S-NPP** during 2012–2025 is the true visual proof that the calibration works.
  4. **Hard-Coded Validation Badge:** `App.tsx` line 22 hard-codes `report.slices['veg/conf2']` (un-nested LOYO WAPE) regardless of the user's selected filters. It should display the **nested LOYO WAPE** (`data/validation_nested/report.json`) matching the active filter (`18.4%` LK, `11.8%` CA, `9.7%` NSW for `veg/conf2+3`).

---

## Part 3: Are Current Analytics & Insights Useful? What Should We Fix or Add?

### 3.1 Honest Evaluation of Current Analytics

| Current Feature | Useful? | Why / Audit Verdict |
|---|---|---|
| **1. Burning Activity Calendar (`Calendar.tsx`)** | ✅ **Yes (Core)** | Directly answers the challenge objective. Once the 2000–2005 blank-out bug (`r.month < month`) and diverging anomaly palette are fixed, this is your centerpiece visual. |
| **2. Month-in-Context Strip & Situation Brief PDF** | ✅ **Yes (High Value)** | Gives emergency managers an immediate, accurate readout (`cell-days`, `historical median`, `percentile`, `transfer range`) and a clean 1-page brief with zero hallucinated numbers. |
| **3. Normalized Region Comparison (` per 1,000 km²`)** | ✅ **Yes (High Value)** | Newly added (`RegionComparison.tsx`); normalizes by exact H3 member area so LK ($72\text{k km}^2$), CA ($423\text{k km}^2$), and NSW ($818\text{k km}^2$) can be compared fairly. Needs the missing-slice fix (1.4). |
| **4. Season Timing Trend Cards (`SeasonInsights.tsx` — "Is the Rhythm Changing?")** | ❌ **Not Useful as Built** | **All 24 trend cards across all 3 regions (`LK`, `CA`, `NSW`) and both eras (`2013+` and `2000+`) currently show `"No directional shift" (0.0 mo/dec)` or `"Insufficient evidence"`!** Why? Because taking the median pairwise slope (Theil–Sen) of coarse integer month indices ($0..11$) where $>50\%$ of years tie on the exact same month index mathematically forces the median slope to `0.00`! Worse, in **NSW**, `SeasonInsights` reports **April** as the peak fire month in **16 of 25 years** and duration as **10 months (Aug–May)** almost every year because autumn agricultural stubble burning and hazard-reduction burns produce more active cell-days than summer bushfires in non-megafire years. |
| **5. Experimental Event Candidates (`EventsPanel.tsx`)** | 🟡 **Secondary Only** | Useful as an exploratory drill-down for a selected month, and its cautions are very honest. However, because single incidents split into multiple fragments (e.g., Gospers Mountain split across fragments) and satellites are not harmonized at the event level, it should stay an optional map drill-down rather than a headline analytic. |

---

### 3.2 High-Value, 100% Accurate Analytics to Add (From Existing Data)

Instead of showing four trend cards that always read `"No directional shift"` / `"Insufficient evidence"`, you can compute four high-impact, scientifically rock-solid analytics directly from your existing datasets:

#### Addition A: Held-Out Overlap Parity Chart & Annual Ranking Proof (in `SeamTest.tsx`)
- **What it shows:** In `SeamTest.tsx`, add a third toggle or overlay—**"Overlap Validation (2012–2025 Held-Out)"**—plotting **out-of-sample MODIS-transferred predictions ($\hat{V}_{\text{pred}}$ with P10–P90 band) vs. actual observed Suomi-NPP ($V_{\text{obs}}$)** from `data/validation_nested/predictions.parquet`.
- **Why it wins:**
  - Shows visually and numerically that out-of-sample predictions track observed VIIRS both monthly (WAPE **9.7%–18.4%**) and annually (annual WAPE **4.5%–7.7%**, Spearman rank correlation **$\rho = 0.934$ in LK, $0.912$ in CA, $0.940$ in NSW**), with empirical 80%-interval coverage of **79.5% (LK), 85.0% (CA), and 86.8% (NSW)**.
  - Directly proves to judges that year-to-year rankings and critical fire peaks are preserved across the sensor divide.

#### Addition B: 12-Month Climatological Regime Envelope vs. Selected Year (in `SeasonInsights.tsx`)
- **What it shows:** Replace or augment the single-year cumulative bar chart with a **Seasonal Regime Climatology Curve**: for each of the 12 months (Jan–Dec, or Jul–Jun for NSW), plot the **25-year historical median line + interquartile range (P25–P75 shaded band) + P10–P90 outer envelope**, with the **selected season overlaid in bold**.
- **Why it wins:**
  - Directly answers the challenge prompt (*"examine historical fire patterns, unusual conditions, and critical periods"*).
  - Makes the three contrasting fire regimes immediately visible without flawed integer-month thresholds:
    - **Sri Lanka:** Clearly shows the **bimodal** agricultural burning regime (minor February–March peak + major July–September Yala dry-season peak, separated by monsoon troughs).
    - **California:** Shows the sharp June–November wildland fire window and highlights extreme autumn anomalies (e.g., Aug–Oct 2020).
    - **NSW:** Clearly reveals the **dual-peak structure**—the summer bushfire window (Nov–Jan, which explodes during 2019/20 Black Summer) versus the regular April–May agricultural stubble / hazard-reduction burn peak!

#### Addition C: Continuous Activity & Extreme-Month Trends (Replacing the `0.0 mo/dec` Integer Timing Trends)
- **What it shows:** Instead of Theil–Sen slopes on integer month indices ($0..11$) that always evaluate to `0.0 mo/decade`, report **continuous, informative multi-year metrics** (comparing the first half of the record vs. the latest decade, with bootstrap/Mann–Kendall p-values or clear distribution shifts):
  1. **Annual Harmonized Activity (`cell-days / yr` & `per 1,000 km²`):** How total annual burning volume has changed across the 25-year record.
  2. **Frequency of Extreme Fire Months (`months > 2× historical median` or `> 90th percentile` per 5-year period):** Shows whether severe fire months are occurring more frequently.
  3. **Peak-3-Month Concentration Share (`% of annual activity in top 3 months`):** Measures whether burning is concentrating into sharper seasonal spikes or spreading across the year.
  4. **Sub-Season Center of Gravity (Activity-Weighted Mean Month / Circular Centroid):** Unlike the integer month of the 10%/90% crossing, the continuous activity-weighted timing centroid (in days/months) detects subtle seasonal shifts without collapsing to `0.0` due to integer rounding.

#### Addition D: Daytime vs. Nighttime & Fire Radiative Power (FRP) Regime Fingerprint
- **What it shows:** Your raw archive (`data/raw/`) and `data/harmonized/*_cells.parquet` already contain `frp` and `daynight` (`D` vs `N`). Adding a compact **Regime & Intensity Fingerprint** (or including `frp` and `day_fraction` in the monthly/cell exports) shows:
  - **Mean FRP per detection (`MW`)** and **Nighttime detection share (`% Night`)**.
- **Why it wins:**
  - Physically explains *why* the fire regimes differ and resolves the NSW April peak question with hard satellite physics:
    - **Sri Lanka:** Small, cool daytime agricultural burns (low mean FRP $\sim 6\text{ MW}$ on VIIRS, almost $100\%$ daytime).
    - **NSW April vs. December:** April agricultural/prescribed burns are predominantly low-FRP daytime burns, whereas December–January bushfires (like 2019/20 Black Summer) have high FRP and a large **nighttime burning fraction** (fires burning actively through the night).
    - **California Megafires:** Extreme FRP ($>50\text{–}200\text{ MW}$) and high nighttime persistence during major complex fires.

#### Addition E: Top Historical Extremes & Sub-Region Hotspot Table
- **What it shows:** A concise **"Historical Extremes & District Breakdown"** card showing:
  1. **Top 5 Highest-Activity Months & Seasons on Record** for the selected region/AOI (with value, multiple of median, and percentile).
  2. **Top 5 Sub-Regions (Districts / Counties / LGAs)** in the selected month or season (ranked by both total cell-days and density per $1{,}000\text{ km}^2$, with a data-support badge).

---

## Summary Action Checklist (In Order of Impact)

1. **Fix `coverage.py` & Satellite Outages (Part 1.1 & 1.2):**
   - Stop marking `0` local detections in Sri Lanka's monsoon as `'missing'` when MODIS/S-NPP is active globally (restores 8 lost pre-2012 years in LK and fixes October 2026 in `RegionComparison`).
   - Gap-fill the 57 S-NPP outage days (especially `2022-08` and `2024-07`) using NOAA-20 on outage dates, and mark `2001-06` / `2002-03` Terra outages as `'provisional'`.
2. **Fix Sub-Region `unallocatable_no_modis` Poisoning & Missing Slices (Part 1.3 & 1.4):**
   - Ensure $M=0 \implies \hat{V}=0$ (or allocate `conf=3` by `conf 2+3` MODIS share when $M_{\text{conf=3}}=0$) so Sri Lankan districts don't lose all 11 pre-2012 years under default `Nominal + High` filters.
   - Emit zero-filled slices for sparse category/confidence pairs so `Industrial` and `Offshore` never break `RegionComparison`.
3. **Fix Calendar Baseline, Diverging Anomaly Scale & Map Scaling (Part 2.1 & 2.2):**
   - Benchmark Calendar `Anomaly` and `Percentile` modes against the **full multi-year eligible climatology** (eliminating the 60 greyed-out 2000–2005 cells), apply a **diverging colorblind-safe ramp centered at $1.0\times$ median**, and fix `FireMap.tsx` to use a consistent scale across months.
4. **Upgrade `SeamTest.tsx` with Held-Out Overlap & NSW Fire-Year Support (Part 2.3 & 3.2A):**
   - Plot the held-out nested LOYO predictions (`data/validation_nested/predictions.parquet`) against observed S-NPP for 2012–2025, use July–June fire years for NSW, exclude 1-month year 2000 from annual totals, and wire the validation badge to the nested LOYO report.
5. **Upgrade `SeasonInsights.tsx` with the 12-Month Climatological Envelope & Continuous Metrics (Part 3.2B–E):**
   - Add the 12-month climatological median + IQR/P90 envelope chart, replace the `0.0 mo/dec` integer month slopes with continuous activity/extreme-month/centroid metrics, and surface Top-5 Historical Extremes & District Rankings.
