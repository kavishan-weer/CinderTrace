"""Build real region outlines + sub-regions (districts / counties / LGAs) from geoBoundaries,
and the 0.05-deg grid-cell -> sub-region membership used to clip the pipeline.
Usage: python -m pipeline.boundaries
"""
import json, pathlib
import numpy as np, pandas as pd
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree
from .regions import REGIONS

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = ROOT / "data" / "boundaries"
CELL = 0.05
COAST_BUFFER = 0.03  # deg; keeps coastal cells whose centre is just offshore but whose pixel is on land

def load(name):
    return json.load(open(B / name))["features"]

def feats(fs, key="shapeName"):
    return [(f["properties"][key], shape(f["geometry"]).buffer(0)) for f in fs]

def build(region):
    if region == "lk":
        outline = unary_union([g for _, g in feats(load("lka_adm0.geojson"))])
        subs = feats(load("lka_adm2.geojson"))
    elif region == "ca":
        outline = dict(feats(load("usa_adm1.geojson")))["California"]
        near = prep(outline.simplify(0.0005).buffer(0.02))
        subs = [(n, g) for n, g in feats(load("usa_adm2.geojson")) if near.contains(g.representative_point())]
    elif region == "nsw":
        outline = dict(feats(load("aus_adm1.geojson")))["New South Wales"]
        near = prep(outline.simplify(0.0005).buffer(0.02))
        subs = [(n, g) for n, g in feats(load("aus_adm2.geojson")) if near.contains(g.representative_point())]
    # cell membership
    x0, y0, x1, y1 = REGIONS[region]["bbox"]
    cxs = np.arange(int(np.floor(x0 / CELL)), int(np.floor(x1 / CELL)) + 1)
    cys = np.arange(int(np.floor(y0 / CELL)), int(np.floor(y1 / CELL)) + 1)
    outline = outline.simplify(0.0005)  # ~50 m, far below the 5 km grid; keeps point-in-polygon fast
    zone = prep(outline.buffer(COAST_BUFFER))
    geoms = [g for _, g in subs]
    tree = STRtree(geoms)
    rows = []
    for cx in cxs:
        for cy in cys:
            p = Point((cx + 0.5) * CELL, (cy + 0.5) * CELL)
            if not zone.contains(p):
                continue
            hit = [i for i in tree.query(p, predicate="within")]
            sub = hit[0] if hit else int(tree.nearest(p)) if geoms else -1
            rows.append((int(cx), int(cy), int(sub)))
    members = pd.DataFrame(rows, columns=["cx", "cy", "sub"])
    members.to_parquet(B / f"{region}_members.parquet", index=False)
    # web-friendly simplified outputs
    def fc(items, props):
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": props(i, n), "geometry": mapping(g.simplify(0.003))} for i, (n, g) in enumerate(items)]}
    (B / f"{region}_region.geojson").write_text(json.dumps(fc([(REGIONS[region]["name"], outline)], lambda i, n: {"id": 0, "name": n})))
    (B / f"{region}_subs.geojson").write_text(json.dumps(fc(subs, lambda i, n: {"id": i, "name": n})))
    print(f"{region}: outline ok, {len(subs)} sub-regions, {len(members):,} grid cells inside (bbox had {len(cxs)*len(cys):,})")

if __name__ == "__main__":
    import sys
    for r in (sys.argv[1:] or list(REGIONS)):
        build(r)
