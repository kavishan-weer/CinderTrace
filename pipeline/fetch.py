"""Phase 1 / step 0: pull point-level detections per region-year from the
portolan-mirrors firms-catalog (GeoParquet on Source Cooperative) into slim local Parquet.
Resumable: existing files are skipped.   Usage: python -m pipeline.fetch [lk ca nsw] [--years 2000-2026]
"""
import sys, time, argparse, pathlib, concurrent.futures as cf
import duckdb
from .regions import REGIONS

BASE = "https://data.source.coop/portolan-mirrors/firms-catalog/detections/year={y}/detections.parquet"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"

SQL = """
COPY (
  SELECT acq_date, acq_datetime, ST_X(geometry) AS lon, ST_Y(geometry) AS lat,
         satellite, sensor, quality, frp, daynight, confidence, confidence_pct,
         type, scan, track, brightness, bright_ti4
  FROM read_parquet('{url}')
  WHERE ST_Within(geometry, ST_MakeEnvelope({x0},{y0},{x1},{y1}))
) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
"""

def fetch_one(region, year, retries=3):
    out = OUT / region / f"{year}.parquet"
    if out.exists():
        return region, year, "skip", 0
    out.parent.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = REGIONS[region]["bbox"]
    tmp = out.with_suffix(".tmp")
    for attempt in range(retries):
        try:
            t = time.time()
            c = duckdb.connect()
            c.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
            c.execute(SQL.format(url=BASE.format(y=year), x0=x0, y0=y0, x1=x1, y1=y1, out=tmp))
            n = c.execute(f"SELECT count(*) FROM read_parquet('{tmp}')").fetchone()[0]
            tmp.rename(out)
            return region, year, "ok", n, round(time.time() - t, 1)
        except Exception as e:
            err = str(e)[:120]
            time.sleep(3 * (attempt + 1))
    return region, year, f"FAIL {err}", 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("regions", nargs="*", default=list(REGIONS))
    ap.add_argument("--years", default="2000-2026")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    y0, y1 = map(int, a.years.split("-"))
    jobs = [(r, y) for r in a.regions for y in range(y0, y1 + 1)]
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda j: fetch_one(*j), jobs):
            print(*res, flush=True)
    print("DONE", flush=True)
