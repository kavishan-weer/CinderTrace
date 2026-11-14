"""Phase 1: categorize (never drop) -> aggregate -> harmonize MODIS to VIIRS-equivalent per category -> validate.

Categories (every detection is kept and tagged):
  cat   : veg | volcano | static | offshore
          Assigned per H3 resolution-6 cell so that categories are disjoint and additive. A cell is
          classified by repeated, majority type flags (see cellcat SQL), otherwise veg. NRT rows (type NULL) inherit the category of their cell, which fixes the
          catalog's missing `type` in recent data.
  conf  : 1 low | 2 nominal | 3 high on a common display scale.
          VIIRS: l/n/h as published. MODIS: 0-29 / 30-79 / 80-100 (the FIRMS display convention; the
          catalog itself publishes no crosswalk, so this is a documented convention, not a calibration).
          A cell-day takes the max confidence among its detections for that sensor family.
  fam   : modis (Terra+Aqua, deduplicated per cell-day) | terra | snpp | n20 | n21

Unit: fire-active cell-days (robust to resolution + overpass differences), plus raw detections and FRP.

Harmonization (per region x cat x conf slice, fit on 2012+ overlap, leave-one-year-out validated):
  naive   V = k*M          strat  V = k_month*M          loglog  log(V+1) = a_month + b*log(M+1)
Slices with too little overlap data fall back to the naive ratio and are flagged `low_data`.

Outputs (data/harmonized/):
  <region>_cells.parquet    h3_cell,lon,lat,area_km2,sub,month,fam,cat,conf,cell_days,detections,frp   (map + filters)
  <region>_monthly.parquet  month,cat,conf,modis_raw,viirs_snpp_raw,harmonized,lo,hi,source,model,low_data
  <region>_report.json      per-slice validation + seam test
Usage: python -m pipeline.harmonize [lk ca nsw]
"""
import sys, json, pathlib
import numpy as np, pandas as pd, duckdb, h3
from .regions import REGIONS
from .grid import H3_RESOLUTION
from .coverage import build_coverage, attach_coverage

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "harmonized"
CATS = ["veg", "volcano", "static", "offshore"]
CONF = [1, 2, 3]
OVERLAP_START = pd.Timestamp("2012-02-01")

CELLS_SQL = """
WITH src0 AS (
  SELECT *, to_h3(lat, lon) AS h3_cell,
    CASE WHEN satellite='Terra' THEN 'terra' WHEN satellite='Aqua' THEN 'aqua'
         WHEN satellite='Suomi-NPP' THEN 'snpp' WHEN satellite='NOAA-20' THEN 'n20'
         WHEN satellite='NOAA-21' THEN 'n21' END AS famr,
    CASE WHEN sensor='MODIS' THEN (CASE WHEN confidence_pct < 30 THEN 1 WHEN confidence_pct < 80 THEN 2 ELSE 3 END)
         ELSE (CASE confidence WHEN 'l' THEN 1 WHEN 'n' THEN 2 WHEN 'h' THEN 3 ELSE 2 END) END AS conf
  FROM read_parquet('{glob}')
),
src AS (SELECT s0.*, m.sub FROM src0 s0 JOIN members m USING (h3_cell)),
cellstat AS (  -- labeled (science-quality) rows only
  SELECT h3_cell, count(*) n,
         count(*) FILTER (WHERE type=1) n1, count(*) FILTER (WHERE type=2) n2, count(*) FILTER (WHERE type=3) n3,
         count(DISTINCT year(acq_date)) FILTER (WHERE type=2) yrs2
  FROM src WHERE type IS NOT NULL GROUP BY h3_cell
),
cellcat AS (  -- persistent-source rule: one stray flag must not turn a wildfire cell into 'static'
  SELECT h3_cell, CASE
      WHEN n1 >= 3 AND n1 * 2 >= n THEN 'volcano'
      WHEN n2 >= 10 AND n2 * 2 >= n AND yrs2 >= 3 THEN 'static'
      WHEN n3 >= 3 AND n3 * 2 >= n THEN 'offshore'
      ELSE 'veg' END AS cat
  FROM cellstat
  UNION ALL  -- cells seen only in NRT (no labels) default to veg
  SELECT DISTINCT h3_cell, 'veg' FROM src WHERE (h3_cell) NOT IN (SELECT h3_cell FROM cellstat)
),
d AS (  -- per sensor-family cell-day
  SELECT h3_cell, any_value(sub) sub, acq_date, famr AS fam, max(conf) conf, count(*) n, sum(frp) frp FROM src GROUP BY h3_cell, acq_date, famr
  UNION ALL
  SELECT h3_cell, any_value(sub), acq_date, 'modis', max(conf), count(*), sum(frp) FROM src WHERE famr IN ('terra','aqua') GROUP BY h3_cell, acq_date
)
SELECT d.h3_cell, any_value(d.sub) AS sub, date_trunc('month', d.acq_date) AS month, d.fam, c.cat, d.conf,
       count(*) AS cell_days, sum(d.n) AS detections, sum(d.frp) AS frp
FROM d JOIN cellcat c USING (h3_cell)
GROUP BY d.h3_cell, date_trunc('month', d.acq_date), d.fam, c.cat, d.conf
"""

def build_cells(region):
    c = duckdb.connect()
    c.create_function("to_h3", lambda lat, lon: h3.latlng_to_cell(lat, lon, H3_RESOLUTION),
                      ["DOUBLE", "DOUBLE"], "VARCHAR")
    members = pd.read_parquet(ROOT / "data" / "boundaries" / f"{region}_members.parquet")
    if "h3_cell" not in members or not all(h3.get_resolution(x) == H3_RESOLUTION for x in members.h3_cell):
        raise ValueError("Rebuild boundaries with python -m pipeline.boundaries")
    c.register("members", members)
    df = c.execute(CELLS_SQL.format(glob=str(RAW / region / "*.parquet"))).df()
    df["month"] = pd.to_datetime(df["month"])
    df = df.merge(members[["h3_cell", "lon", "lat", "area_km2"]], on="h3_cell", validate="many_to_one")
    for col in ("cell_days", "detections"):
        df[col] = df[col].astype("int64")
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / f"{region}_cells.parquet", index=False)
    return df

def slice_series(cells, cat, conf, idx):
    s = cells[(cells.cat == cat) & (cells.conf == conf)]
    piv = s.groupby(["month", "fam"]).cell_days.sum().unstack(fill_value=0)
    out = pd.DataFrame(index=idx)
    for f in ("modis", "terra", "snpp"):
        out[f] = piv[f].reindex(idx).fillna(0).astype(float) if f in piv else 0.0
    return out

def fit_models(d):
    k = d.snpp.sum() / max(d.modis.sum(), 1)
    km = {m: (g.snpp.sum() / max(g.modis.sum(), 1)) for m, g in d.groupby(d.index.month)}
    for m in range(1, 13):
        km.setdefault(m, k)
    X, Y, months = np.log1p(d.modis.values), np.log1p(d.snpp.values), d.index.month.values
    D = np.column_stack([X] + [(months == m).astype(float) for m in range(1, 13)])
    coef, *_ = np.linalg.lstsq(D, Y, rcond=None)
    b, a = coef[0], coef[1:]
    return {
        "naive": lambda M, mo: k * np.asarray(M, float),
        "strat": lambda M, mo: np.array([km[m] for m in mo]) * np.asarray(M, float),
        "loglog": lambda M, mo: np.maximum(0, np.expm1(b * np.log1p(np.asarray(M, float)) + a[np.asarray(mo) - 1])),
    }

def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    ss_total = np.square(y - y.mean()).sum()
    return {"WAPE": float(np.abs(y - p).sum() / max(y.sum(), 1)),
            "bias": float((p.sum() - y.sum()) / max(y.sum(), 1)), "MAE": float(np.abs(y - p).mean()),
            "R2": float(1 - np.square(y - p).sum() / ss_total) if ss_total > 0 else None}

def loyo(d):
    ov = d[(d.index >= OVERLAP_START) & d.get("training_ok", pd.Series(True, index=d.index)) & d.modis.notna() & d.snpp.notna()]
    preds = {m: pd.Series(index=ov.index, dtype=float) for m in ("naive", "strat", "loglog")}
    for y in sorted(set(ov.index.year)):
        tr, te = ov[ov.index.year != y], ov[ov.index.year == y]
        f = fit_models(tr)
        for m in preds:
            preds[m].loc[te.index] = f[m](te.modis.values, te.index.month)
    val = {m: metrics(ov.snpp, preds[m]) for m in preds}
    resid = {m: np.log1p(ov.snpp.values) - np.log1p(preds[m].values) for m in preds}
    return val, resid, ov

def harmonize_slice(d):
    """d: modis, terra, snpp monthly cell-days. Returns (frame, report)."""
    d = d.copy()
    d["modis"] = d.modis.astype(float)
    d["modis_raw"] = d.modis
    terra_only = d.index < "2002-08-01"
    ref = d[(d.index >= "2003-01-01") & (d.index < "2012-01-01")]
    ratio = {m: (g.modis.sum() / g.terra.sum()) if g.terra.sum() >= 20 else 1.8 for m, g in ref.groupby(ref.index.month)}
    d.loc[terra_only, "modis"] = [d.terra[i] * ratio.get(i.month, 1.8) for i in d.index[terra_only]]
    if "modis_status" in d:
        d.loc[d.modis_status == "missing", "modis"] = np.nan
    ov = d[(d.index >= OVERLAP_START) & d.get("training_ok", pd.Series(True, index=d.index)) & d.modis.notna() & d.snpp.notna()]
    low_data = len(ov) < 60 or ov.snpp.sum() < 300
    observed = (d.index >= OVERLAP_START) & d.snpp.notna()
    if low_data:
        k = ov.snpp.sum() / ov.modis.sum() if len(ov) and ov.modis.sum() > 0 else float("nan")
        pred = k * d.modis.values
        lo, hi, model, val = pred * 0.5, pred * 2.0, "naive", None
    else:
        val, resid, ov = loyo(d)
        model = min(("strat", "loglog"), key=lambda m: val[m]["WAPE"])
        lo_q, hi_q = np.quantile(resid[model], [0.1, 0.9])
        pred = fit_models(ov)[model](d.modis.values, d.index.month)
        lo, hi = np.expm1(np.log1p(pred) + lo_q), np.expm1(np.log1p(pred) + hi_q)
    pred = np.maximum(pred, 0)
    lo, hi = np.minimum(pred, np.maximum(lo, 0)), np.maximum(pred, hi)
    out = pd.DataFrame({
        "month": d.index, "modis_raw": d.modis_raw.values, "viirs_snpp_raw": d.snpp.values,
        "harmonized": np.where(observed, d.snpp.values, pred),
        "lo": np.where(observed, d.snpp.values, lo), "hi": np.where(observed, d.snpp.values, hi),
        "source": np.where(observed, "viirs_observed", np.where(np.isfinite(pred), "modis_transferred", "missing")),
        "modis_status": d.get("modis_status", "inferred_available"),
        "snpp_status": d.get("snpp_status", "inferred_available"),
        "model": model, "low_data": low_data})
    selected_status = np.where(observed, d.get("snpp_status", "inferred_available"), d.get("modis_status", "inferred_available"))
    out["period_status"] = np.where(out.source == "missing", "missing", selected_status)
    out["comparison_eligible"] = out.period_status == "inferred_available"
    out["training_eligible"] = d.get("training_ok", False).to_numpy() if "training_ok" in d else False
    return out, {"model": model, "low_data": bool(low_data), "overlap_months": int(len(ov)), "validation_LOYO_monthly": val}

def seam(series_raw, series_h):
    def ann(s, y): return float(s[s.index.year == y].sum())
    return {"raw_merged_2012_over_2011": ann(series_raw, 2012) / max(ann(series_raw, 2011), 1),
            "harmonized_2012_over_2011": ann(series_h, 2012) / max(ann(series_h, 2011), 1)}

def run(region):
    cells = build_cells(region)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    as_of = pd.Timestamp(datetime.now(ZoneInfo('Asia/Colombo')).date())
    idx = pd.date_range("2000-11-01", as_of.replace(day=1), freq="MS")
    coverage = build_coverage(RAW / region / "*.parquet", idx, as_of)
    coverage.to_parquet(OUT / f"{region}_coverage.parquet", index=False)
    frames, slices = [], {}
    for cat in CATS:
        for conf in CONF:
            d = attach_coverage(slice_series(cells, cat, conf, idx), coverage)
            if d.modis.sum() + d.snpp.sum() < 10:
                continue
            f, rep = harmonize_slice(d)
            f["cat"], f["conf"] = cat, conf
            frames.append(f); slices[f"{cat}/conf{conf}"] = rep
    monthly = pd.concat(frames, ignore_index=True)
    monthly.to_parquet(OUT / f"{region}_monthly.parquet", index=False)
    # seam test for two filter presets
    def preset(cats, confs):
        m = monthly[monthly.cat.isin(cats) & monthly.conf.isin(confs)].groupby("month")[["modis_raw", "viirs_snpp_raw", "harmonized"]].sum()
        return seam(m.modis_raw + m.viirs_snpp_raw, m.harmonized)
    rep = {"region": REGIONS[region]["name"], "grid": {"system": "H3", "resolution": H3_RESOLUTION}, "coverage_basis": "inferred archive availability; not observation coverage", "as_of": str(as_of.date()), "slices": slices,
           "seam_default_veg_nom_high": preset(["veg"], [2, 3]),
           "seam_all_data": preset(CATS, CONF)}
    (OUT / f"{region}_report.json").write_text(json.dumps(rep, indent=2))
    return rep, cells, monthly

if __name__ == "__main__":
    for r in (sys.argv[1:] or list(REGIONS)):
        rep, cells, monthly = run(r)
        print(f"\n=== {rep['region']}   cells rows: {len(cells):,}")
        tot = cells[cells.fam == "snpp"].groupby("cat").detections.sum().to_dict()
        print("  S-NPP detections by category:", tot)
        for k, s in rep["slices"].items():
            v = s["validation_LOYO_monthly"]
            if v is None:
                print(f"  {k:14s} low_data -> naive fallback (overlap months {s['overlap_months']})")
            else:
                print(f"  {k:14s} best={s['model']:6s} WAPE naive={v['naive']['WAPE']:.3f} -> {v[s['model']]['WAPE']:.3f}  R2={v[s['model']]['R2']:.2f}")
        print("  seam default (veg, nominal+high):", {k: round(x, 2) for k, x in rep["seam_default_veg_nom_high"].items()})
        print("  seam all data:                   ", {k: round(x, 2) for k, x in rep["seam_all_data"].items()})
