"""Recompute browser-export fidelity and a frozen, independent CAL FIRE reference case.

No model is fitted and no ground-truth fire sensitivity is inferred.  Run from the
repository root with .venv/bin/python scripts/export_validation_showcase.py.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import shapely
from shapely.geometry import shape, mapping
from shapely.ops import transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/site-public/validation'
READY = ROOT / 'web/site-public/ready'
SATELLITES = ['Terra', 'Aqua', 'Suomi-NPP', 'NOAA-20', 'NOAA-21']


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, separators=(',', ':'), allow_nan=False)+'\n')


def source_key(row):
    return (int(pd.Timestamp(row.acq_datetime).timestamp()), float(row.longitude),
            float(row.latitude), SATELLITES.index(row.satellite),
            float(row.frp) if pd.notna(row.frp) else None, str(row.confidence),
            int(row.type) if pd.notna(row.type) else None,
            0 if row.quality == 'sp' else 1, str(row.daynight))


def browser_key(row):
    return tuple(row[:8])+tuple(row[10:11])


def source_reconciliation():
    canonical = ROOT/'data/atlas/canonical_lk_2000_2024_v1'
    manifest = read(canonical/'manifest.json')
    for name, receipt in manifest['files'].items():
        p = canonical/name
        assert p.stat().st_size == receipt['bytes'] and digest(p) == receipt['sha256'], name
    source = pq.read_table(canonical/'observations.parquet').to_pandas()
    ready_manifest = read(READY/'manifest.json')
    annual = []
    months = []
    for year in range(2000, 2025):
        path = READY/'lk'/f'native-{year}.json.gz'
        file_receipt = ready_manifest['files'][f'lk/native-{year}.json.gz']
        assert digest(path) == file_receipt['sha256']
        browser = json.loads(gzip.decompress(path.read_bytes()))
        assert browser['source_sha256'] == manifest['files']['observations.parquet']['sha256']
        originals = source[source.year.eq(year)]
        expected = Counter(source_key(r) for r in originals.itertuples())
        actual = Counter(browser_key(r) for r in browser['rows'])
        missing = sum((expected-actual).values())
        extra = sum((actual-expected).values())
        matched = sum((expected & actual).values())
        expected_month = Counter((pd.Timestamp(r.acq_datetime).month, r.satellite) for r in originals.itertuples())
        actual_month = Counter((datetime.fromtimestamp(r[0], timezone.utc).month, SATELLITES[r[3]]) for r in browser['rows'])
        for month in range(1, 13):
            for satellite in SATELLITES:
                a, b = expected_month[month,satellite], actual_month[month,satellite]
                months.append({'year':year,'month':month,'satellite':satellite,'reference':a,'exported':b,'difference':b-a})
        annual.append({'year':year,'reference':len(originals),'exported':len(browser['rows']),'matched':matched,'missing':missing,'extra':extra,'file_sha256':file_receipt['sha256']})
        assert not missing and not extra and sum(actual.values()) == browser['count']
    mismatch = read(ROOT/'docs/atlas_lk_2022_2024_verification.json')['NOAA21_NRT_vs_standard']
    history = read(ROOT/'docs/atlas_history_2000_2021_verification.json')
    pilot = read(ROOT/'docs/atlas_2023_official_verification.json')
    benchmark = read(ROOT/'docs/atlas_lk_2022_2024_verification.json')
    return {
        'kind':'authoritative_source_reconciliation',
        'title':'Sri Lanka / source-to-screen fidelity',
        'scope':'All published native records in the Sri Lanka 2000–2024 standard-data checkpoint; no UI filters applied.',
        'units':'satellite pixel observations',
        'reference':'Verified NASA FIRMS standard-data responses, frozen local checkpoint',
        'observations':len(source),'matched':sum(a['matched'] for a in annual),
        'missing':sum(a['missing'] for a in annual),'extra':sum(a['extra'] for a in annual),
        'years':annual,'monthly_satellite':months,
        'verified_raw_requests':history['verified_raw_requests']+pilot['verified_requests']+benchmark['verified_requests'],
        'reference_sha256':manifest['files']['observations.parquet']['sha256'],
        'boundary_sha256':manifest['boundary_sha256'],
        'manifest_sha256':digest(canonical/'manifest.json'),
        'comparison_fields':['UTC acquisition second','longitude','latitude','satellite','FRP','native confidence','published type','processing quality','day/night'],
        'comparison_method':'Exact multiset comparison of nine browser-exported native fields against the verified standard checkpoint. All source files and every compared browser file are SHA256 checked before evaluation. Monthly-by-satellite totals are independently reconstructed.',
        'historical_capture':'2026-11-14',
        'noaa21_audit':{'year':2024,'nrt_records':mismatch['mirror_rows'],'standard_records':mismatch['official_rows'],'shared_native_keys':mismatch['shared_rows'],'standard_only_keys':mismatch['official_rows_missing_in_mirror'],'nrt_only_keys':mismatch['mirror_rows_not_in_official'],'decision':'The app uses the verified standard stream. The different NRT capture is retained as an audit, never stacked or treated as a matching standard stream.'},
        'limits':['NASA FIRMS and the catalogue mirror share an upstream detection algorithm. Agreement is source fidelity, not independent physical-fire truth.','This result does not validate Fire Harmony estimates, sensor harmonization, observing coverage, false-positive rates, incident counts, burned area or forecasts.','California, New South Wales, and Sri Lanka 2025 onward are not covered by this authoritative-response reconciliation.','The earliest archive year is partial: November–December 2000. Fleet changes make raw annual sums incomparable as fire trends.'],
        'source_links':[{'label':'NASA FIRMS archive','url':'https://firms.modaps.eosdis.nasa.gov/download/'},{'label':'Catalogue source','url':'https://github.com/portolan-mirrors/firms-catalog'}]
    }


def perimeter_case():
    path = OUT/'calfire-creek-reference.json'
    query = read(OUT/'calfire-query.json')
    assert digest(path) == query['response_sha256']
    raw = read(path)
    matches = [f for f in raw['features'] if f['properties'].get('UNIT_ID') == 'SNF' and f['properties'].get('ALARM_DATE') == 1599177600000]
    assert len(matches) == 1, 'Fixed case must identify one Sierra National Forest Creek perimeter'
    feature = matches[0]
    properties = feature['properties']
    geometry = shapely.make_valid(shape(feature['geometry']))
    assert properties['YEAR_'] == 2020 and properties['FIRE_NAME'].upper() == 'CREEK'
    begin = datetime.fromtimestamp(properties['ALARM_DATE']/1000, timezone.utc).date()
    end = datetime.fromtimestamp(properties['CONT_DATE']/1000, timezone.utc).date()
    first = int(pd.Timestamp(begin).tz_localize('UTC').timestamp())
    last = int((pd.Timestamp(end)+pd.Timedelta(days=1)).tz_localize('UTC').timestamp())
    native_file = READY/'ca/native-2020.json.gz'
    native = json.loads(gzip.decompress(native_file.read_bytes()))
    year = 2020
    # A predeclared local evaluation rectangle: final perimeter bounds expanded by 0.05 degrees.
    w,s,e,n = geometry.bounds
    bbox = [w-.05,s-.05,e+.05,n+.05]
    rows = [r for r in native['rows'] if first <= r[0] < last and bbox[0] <= r[1] <= bbox[2] and bbox[1] <= r[2] <= bbox[3]]
    points = shapely.points(np.array([r[1] for r in rows]),np.array([r[2] for r in rows]))
    shapely.prepare(geometry)
    inside = shapely.covers(geometry, points)
    project = Transformer.from_crs('EPSG:4326','EPSG:3310',always_xy=True).transform
    unproject = Transformer.from_crs('EPSG:3310','EPSG:4326',always_xy=True).transform
    expanded = transform(unproject,transform(project,geometry).buffer(1000))
    shapely.prepare(expanded)
    near = shapely.covers(expanded,points)
    satellite = []
    for i,name in enumerate(SATELLITES):
        mask = np.array([r[3] == i for r in rows])
        satellite.append({'name':name,'local_records':int(mask.sum()),'inside_final_perimeter':int(np.logical_and(mask,inside).sum()),'inside_or_within_1km':int(np.logical_and(mask,near).sum())})
    daily = defaultdict(lambda: [0,0,0])
    for r, hit, nearby in zip(rows,inside,near):
        date = datetime.fromtimestamp(r[0],timezone.utc).date().isoformat()
        daily[date][0] += 1;daily[date][1] += int(hit);daily[date][2] += int(nearby)
    # Render bins preserve all counts, rather than silently sampling points.
    bins = defaultdict(lambda: [0,0,0])
    for r,hit in zip(rows,inside):
        key=(round(r[1]/.005)*.005,round(r[2]/.005)*.005)
        bins[key][0]+=1;bins[key][1]+=int(hit)
    display = [{'lon':round(k[0],6),'lat':round(k[1],6),'count':v[0],'inside_count':v[1]} for k,v in sorted(bins.items())]
    simplified = shapely.simplify(geometry,.0005,preserve_topology=True)
    return {
        'kind':'independent_geographic_reference_case','title':'Creek Fire / California, 2020',
        'reference':'CAL FIRE FRAP final historical fire perimeter','reference_feature':properties,
        'source_url':query['endpoint'],'query_url':query['query_url'],'reference_sha256':query['response_sha256'],'reference_retrieved_utc':datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        'browser_file_sha256':digest(native_file),'native_input_sha256':native['source_sha256'],
        'window_start':begin.isoformat(),'window_end':end.isoformat(),'bbox':bbox,
        'local_records':len(rows),'inside_final_perimeter':int(inside.sum()),'inside_or_within_1km':int(near.sum()),
        'inside_share':float(inside.mean()) if len(rows) else None,
        'by_satellite':satellite,'daily':[{'date':day.date().isoformat(),'local':daily[day.date().isoformat()][0],'inside':daily[day.date().isoformat()][1],'within_1km':daily[day.date().isoformat()][2]} for day in pd.date_range(begin,end,freq='D')],
        'geometry':mapping(simplified),'map_bins':display,
        'method':'All native California records, all satellites/confidence/source types/qualities, whose centres lie in the final-perimeter bounding rectangle expanded by 0.05 degrees, during the inclusive UTC calendar dates in CAL FIRE ALARM_DATE and CONT_DATE. Count point centres covered by the full-resolution final polygon; repeat with a 1 km EPSG:3310 buffer. Display geometry alone is simplified; map bins are 0.005-degree groups and preserve record counts.',
        'limits':['A fixed, retrospective geographic concordance case, not a blind validation cohort, a Fire Harmony model test, or physical-fire sensitivity/specificity.','The final perimeter includes land burned over the entire incident; it is not a daily active-fire perimeter and can contain unburned islands.','Records outside it are not automatically false alarms, and absence inside it is not proof of no fire. Nearby unrelated burning can contribute to this local rectangle.','Different satellites can record the same burning repeatedly. Pixel centres, clouds and observing opportunities differ; overlap is not burned area or incident identification.','CAL FIRE perimeters are an independently maintained geographic reference, but individual perimeter delineation methods may incorporate satellite imagery; statistical independence of every reference input is not claimed.','This selected case does not establish performance in Sri Lanka or NSW, or certify the completeness of the CAL FIRE database.'],
        'reference_credit':'CAL FIRE FRAP and cooperating agencies. Historical fire perimeter dataset; retrieved official ArcGIS service.',
        'source_links':[{'label':'CAL FIRE methods and limitations','url':'https://www.fire.ca.gov/what-we-do/fire-resource-assessment-program/fire-perimeters'},{'label':'California open-data catalogue','url':'https://data.ca.gov/@cal-fire/california-fire-perimeters-all'}]
    }


def main():
    receipt = {'version':1,'generated_utc':datetime.now(timezone.utc).isoformat(),'source_reconciliation':source_reconciliation(),'perimeter_case':perimeter_case(),'claims':{'source_fidelity_checked':True,'independent_perimeter_case_checked':True,'physical_fire_sensitivity_validated':False,'provider_harmonization_validated':False,'forecast_validated':False,'observing_coverage_verified':False}}
    write('showcase.json',receipt)
    print(json.dumps({'source_records':receipt['source_reconciliation']['observations'],'missing':receipt['source_reconciliation']['missing'],'extra':receipt['source_reconciliation']['extra'],'perimeter_local_records':receipt['perimeter_case']['local_records'],'inside':receipt['perimeter_case']['inside_final_perimeter'],'near_1km':receipt['perimeter_case']['inside_or_within_1km']},indent=2))


if __name__=='__main__':
    main()
