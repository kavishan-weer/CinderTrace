# EMBERLINE: Review against the challenge, and how to make it exceptional

## Verdict

**Your science is already top-tier. What judges will actually see is not, yet.**

What I checked: the pipeline, the ML code, the docs, the web source and the screenshots. Both test suites pass (54 Python, 28 frontend).

Your harmonization is validated, the uncertainty is honest, there's a NSW fire-year mode, and the incident cross-checks against CAL FIRE and NSW perimeters are rigorous. Very few Space Apps teams reach this level. The remaining risks: the app covers only 3 hard-coded regions, it has no live data, and the headline "early warning" story in the strategy is contradicted by your own validation.

| Criterion | Now | Why |
|---|---|---|
| Validity | ⭐⭐⭐⭐⭐ | Leave-one-year-out validation, beats the naive baseline in all 9 region × confidence slices, P10–P90 bands, honest gates |
| Relevance | ⭐⭐⭐⭐ | Covers harmonization, calendar, AOI, date range, anomaly view and CSV. Weak spot: "any area of interest" really means only 3 regions |
| Creativity | ⭐⭐⭐⭐ | Seam Test, fire-year mode, events, static-source mask |
| Impact | ⭐⭐⭐ | No live data, and the outlook is excluded from the app |
| Presentation | ⭐⭐⭐ | Heavy hedging in the UI copy, no demo video or slides yet, minified-looking source code |

> [!NOTE]
> **Already handled by you, so not counted as gaps:**
> - **CARTO Basemaps key:** you have one, so the basemap with place names will render.
> - **Deployment:** planned for later.
>
> One reminder for when you deploy: custom areas, raw CSV, the events view and the PDF brief call the **local Python API** (`/api/area`, `/api/exports/*`, `/api/events/*`). That service has to be hosted too, not just the static `dist/`. Also restrict the CARTO key to your deployed domain.

---

## 🔴 Critical gaps (fix these or risk losing)

### 1. The "early warning" story is contradicted by your own results
- Strategy §7 plans to say: *"Our model flagged Black Summer in Aug 2019."* But [fire_outlook.md](file:///Users/kavishanwee/Documents/ignite%20copy/docs/fire_outlook.md) shows **NSW WIS skill is −1% to −4%**, and above-normal Brier skill **fails** the gate in Sri Lanka. [outlook_calibration.md](file:///Users/kavishanwee/Documents/ignite%20copy/docs/outlook_calibration.md) concludes **"App ready: false."**
- A domain judge who asks "show me the hindcast" would sink the pitch.
- **Fix:** take that claim out of the demo. Make the early-warning angle **"Now vs History, live"** instead (gap 2). Present the outlook as a *documented negative result*: "we tested whether weather and ENSO data beat climatology, and they don't yet." Scientists respect that, and it supports your validity score.

### 2. There's no live or near-real-time data
- The archive snapshot is from 2026-11-13. The challenge calls for "early warning" and "compare the current month against the historical median."
- **Fix:** add a scheduled job (GitHub Action, daily) that pulls firms-catalog `live.parquet`, applies the existing category, confidence and harmonization logic, and re-exports the JSON.
- Then add a **month-to-date vs same-day-of-month historical percentile** card: *"Day 14 of November: 92nd percentile for this date."* That gives you a true early-warning feature, and it's cheap to build.

### 3. The challenge says "any area"; you cover 3 regions
- A judge in Brazil or Indonesia can't try it on their own country, and "select an area of interest" is the central user action.
- **Fix, in increasing ambition:**
  1. **Minimum:** state the scope clearly ("3 contrasting fire regimes as validated case studies") and make adding a region a one-command pipeline step. Demo that.
  2. **Exceptional:** build a **global layer**. Precompute global H3 res-4/5 monthly cell-days per sensor family from firms-catalog, fit transfer coefficients **per biome (MODIS land cover or WWF ecoregion) × hemisphere-season**, and validate with leave-one-year-out per biome. Then any polygon on Earth gets a harmonized calendar, with an "extrapolated, lower confidence" badge outside your 3 deep-validated regions. **This alone could separate you from every other team.**

---

## 🟠 Scientific concerns a judge might probe

| # | Concern | Why it matters | Fix |
|---|---|---|---|
| 4 | **The Seam Test uses a single year ratio (2012/2011)** | Real year-to-year variability confounds it. NSW harmonized = **0.72×**, which can look like over-correction | Add the **overlap overlay**: for 2012–2025, plot *MODIS-transferred* and *VIIRS-observed* on the same axes. Two lines on top of each other is the strongest possible proof. Optionally add a structural-break test (Pettitt / CUSUM) on deseasonalized raw vs harmonized series. |
| 5 | **Orbit drift isn't modelled** | Terra and Aqua overpass times drift late in the mission, and the training window (2012+) includes those drift years | Refit on 2012–2019 only, compare the coefficients, and report the sensitivity. One table, one sentence. |
| 6 | **Validation is regional-monthly only, but sub-area and custom-AOI calendars use region-calibrated allocation** | Districts and LGAs inherit coefficients never validated at that scale | Run leave-one-year-out at district level (e.g. LK's 25 districts) and publish an error map. That turns a hidden weakness into a feature: the "confidence per district" shading. |
| 7 | **Unit is "fire-active cell-days"** | Abstract for emergency managers. The challenge says "number of hotspots" | Offer a toggle between **VIIRS-equivalent hotspots** (harmonize `detections` too) and cell-days, plus a **per-1,000 km²** normalization for region comparison. |
| 8 | **Low-confidence slices are still weak** (WAPE 0.30–0.59) | Fine, since nominal+high is the default, but say so up front | Keep the default, and show the per-slice error in the method dialog (already partly done). |
| 9 | **Promised harmonization v2 (LightGBM with FRP/scan) isn't built** | Strategy §3 lists it | Either build it, or add a **physics cross-check**: drop VIIRS detections below a MODIS-detectable FRP threshold to get a "MODIS-equivalent" VIIRS series. It's an independent method that should agree with your statistical one. |

---

## 🟡 Product and UX gaps

10. **The anomaly mode uses the sequential ramp.** `color()` in [analytics.ts](file:///Users/kavishanwee/Documents/ignite%20copy/web/src/analytics.ts) maps 0–2× median onto the same viridis-like ramp. Anomalies need a **diverging, colorblind-safe ramp centred on 1×** (e.g. blue ↔ neutral ↔ orange/brown, log-scaled), so "below normal" reads differently from "low". The challenge explicitly mentions color ramps for similarities and differences.
11. **Too many caveats in the UI.** Labels like "Confidence classes are display conventions", "Experimental", "agency-review cautions" and "inferred archive availability" appear everywhere. Keep that rigor in the method page. In the main UI, use **one confidence badge** (high / medium / low) with a tooltip. Emergency managers need a quick read, not footnotes.
12. **There's no single headline.** The first screen should answer the challenge in one glance: *"This area, this month: 3.4× normal, 96th percentile, highest since 2017."*
13. **Region comparison is missing** (strategy P1). Add LK vs CA vs NSW side by side, normalized per km².
14. **The regime classifier (3C) and grounded AI brief (3D) aren't built.** 3D is cheap with your existing computed stats. A "Explain this area" Gemini summary, constrained to pipeline numbers, makes a good demo moment. 3C is optional.
15. **The events view has no headline "number of fires".** That's reasonable given your validation. Consider showing *"~N fire events (estimated, ±)"* with the CAL FIRE / NSW match rate as the credibility number.

---

## 🔵 Engineering and submission hygiene

16. **Almost everything is uncommitted.** There's one commit ("first commit"), and `ml/`, `tests/`, `web/` and most of `pipeline/` are untracked. Commit in logical steps and push to a public repo.
17. **The code is hard to read.** [App.tsx](file:///Users/kavishanwee/Documents/ignite%20copy/web/src/App.tsx) is 21 KB on 34 lines, and Calendar.tsx is one giant line. Judges who open GitHub will see what looks like minified code. Run Prettier on the frontend before submitting.
18. **Reproducibility.** Generated data is gitignored (428 MB pipeline, 105 MB web). Publish the web dataset as a GitHub Release or Hugging Face dataset, and add a `make all` / one-command reproduce script to the root README.
19. **Submission assets are missing:** a 30-second demo video, a 7-slide deck, a root README with a hero GIF, and a one-page method summary with the validation table and overlap chart.

---

## Recommended priority order

| Order | Item | Effort | Payoff |
|---|---|---|---|
| 1 | Drop the outlook claim and reframe the pitch (gap 1) | S | Avoids a fatal Q&A moment |
| 2 | Overlap overlay chart in the Seam Test (4) + diverging anomaly ramp (10) | S | Strongest visual proof plus a challenge-explicit item |
| 3 | Live NRT + month-to-date percentile card (gap 2, 12) | M | Real early warning |
| 4 | Hotspot-count unit + per-km² + region comparison (7, 13) | S–M | Matches the challenge wording |
| 5 | Commit, Prettier, root README, video, slides (16–19) | S–M | Presentation score |
| 6 | District-level validation map (6) + drift sensitivity (5) | M | Answers expert questions |
| 7 | **Global biome-stratified layer (gap 3)** | L | The "exceptional" differentiator |
| 8 | Grounded Gemini brief (14) | S | Demo polish |
| — | Deploy (frontend + Python API) with the CARTO key restricted to your domain | — | Planned by you |

## Revised demo arc (about 2 min)
1. **Hook:** "Sri Lanka's fires jumped 7.7× in 2012. They didn't. A new satellite arrived." Show the Seam Test, then the **overlap overlay** with the two lines on top of each other.
2. **Proof:** "We beat the naive correction in all 9 slices, with up to 68% less error." Show the validation table.
3. **Insight:** the NSW fire-year calendar, with Black Summer standing out in the diverging anomaly view.
4. **Action:** draw an AOI. "Today: 92nd percentile for mid-November." Download the CSV and the Situation Brief.
5. **Integrity:** "We also tested whether weather and ENSO forecasts beat climatology. They don't yet, so we don't ship them."
