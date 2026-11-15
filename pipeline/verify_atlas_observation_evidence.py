"""Verify returned observation-pilot evidence without requiring original science files.
Checks archived bytes, frozen metadata/method, receipt identities, internal tables
and native fire-mask reconciliation. Does not independently re-read cached NetCDF.
"""
from pathlib import Path
import hashlib,io,json,re,zipfile
import pandas as pd
import numpy as np
import h3
from . import atlas_observation_evidence as e

ROOT=Path(__file__).resolve().parent.parent
DEFAULT_ZIP=ROOT/'cindertrace_atlas_lk_observation_evidence_20261115T001225Z.zip'

def require(condition,message):
    if not condition:raise ValueError(message)

def read_verified_bundle(path):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist();require(len(names)==len(set(names)),'Duplicate bundle members')
        require(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names),'Unsafe member name')
        manifest=json.loads(archive.read('bundle_manifest.json'))
        require(set(names)==set(manifest)|{'bundle_manifest.json'},'Unmanifested bundle member')
        members={}
        for name,r in manifest.items():
            raw=archive.read(name);require(len(raw)==r['bytes'] and e.sha(raw)==r['sha256'],'Changed bundle member: '+name);members[name]=raw
    return members

def nonnegative_integers(frame,columns):
    for col in columns:
        x=pd.to_numeric(frame[col],errors='raise').to_numpy(float)
        require(np.isfinite(x).all() and (x>=0).all() and (x==np.floor(x)).all(),'Invalid count: '+col)

def run(path=None,output=None):
    path=Path(DEFAULT_ZIP if path is None else path);members=read_verified_bundle(path)
    j=lambda name:json.loads(members[name]);table=lambda name:pd.read_parquet(io.BytesIO(members['results/'+name+'.parquet']))
    inv=j('catalogue/inventory.json');frozen=ROOT/'data/atlas/observation_evidence_pilot_v1'
    require(members['catalogue/inventory.json']==(frozen/'inventory.json').read_bytes(),'Pilot catalogue differs from frozen input')
    require(j('results/method.json')==e.POLICY,'Unexpected screening policy')
    require(members['results/research_implementation.py']==Path(e.__file__).read_text().split("if __name__=='__main__':")[0].encode(),'Changed screening implementation')
    for prefix,manifest_name in [('catalogue/','metadata_bundle_manifest.json'),('results/','manifest.json')]:
        inner=j(prefix+manifest_name);receipts=inner.get('files',inner)
        for name,r in receipts.items():
            raw=members[prefix+name];require(len(raw)==r['bytes'] and e.sha(raw)==r['sha256'],'Changed nested member: '+name)
    require(e.sha(members['catalogue/region.geojson'])==e.BOUNDARY_SHA,'Changed study boundary')
    decision=j('results/decision.json');require(decision['inventory_sha256']==e.sha(members['catalogue/inventory.json']),'Wrong inventory reference')
    records={r['id']:r for r in inv['records']};receipts=j('results/download_receipts.json');require(len(receipts)==len(records),'Incomplete science receipts')
    require(len({r['id'] for r in receipts})==len(records),'Duplicate science receipts')
    for r in receipts:
        require(r['id'] in records,'Unknown downloaded granule');meta=records[r['id']]
        require(r['product']==meta['product'] and r['acquisition']==meta['acquisition'],'Wrong downloaded identity')
        require(r['http_status']==200 and r['bytes']>0 and re.fullmatch('[0-9a-f]{64}',r['sha256']) is not None,'Invalid download receipt')
        require(abs(r['bytes']-meta['catalogue_size_mb']*1024**2)<2,'Receipt size differs from catalogue')
    g=table('granule_screening');cells=table('cell_centre_support');daily=table('daily_screen_status');pairs=table('candidate_pair_diagnostics')
    expected={r['id'] for r in records.values() if r['kind']=='fire'}
    require(len(g)==len(expected) and set(g.fire_id)==expected,'Incomplete or duplicate fire screening')
    require(not j('results/failures.json') and decision['failed_or_unavailable']==0,'Run has unavailable science screens')
    require(decision['screened_fire_granules']==len(g)==decision['planned_fire_granules'],'Decision count mismatch')
    for row in g.to_dict('records'):
        meta=records[row['fire_id']]
        for col in ['product','satellite','date','time_start','time_end','day_night']:require(row[col]==meta[col],'Screening metadata mismatch: '+col)
        require(len(row['shape'])==2 and row['shape'][1]==6400,'Unexpected native grid')
    counts=['local_geolocated_centres','nominal_clear_centres','screened_fire_centres','local_residual_bowtie_centres']+['class_'+str(i) for i in range(10)]
    nonnegative_integers(g,counts);require(g[[f'class_{i}' for i in range(10)]].sum(axis=1).eq(g.local_geolocated_centres).all(),'Class total mismatch')
    require(g.screened_fire_centres.le(g.nominal_clear_centres).all() and g.nominal_clear_centres.le(g.local_geolocated_centres).all(),'Invalid screen count ordering')
    require(g.screened_fire_centres.le(g[['class_7','class_8','class_9']].sum(axis=1)).all(),'Screened fires exceed raw fire classes')
    aligned=g[g.alignment_check_pixels.gt(0)];require(aligned.alignment_max_error_degrees.between(0,.01).all(),'Failed sparse alignment')
    require(not cells.duplicated(['fire_id','cell']).any(),'Duplicate support rows')
    require(set(cells.fire_id)<=expected,'Unknown cell-support source');nonnegative_integers(cells,['local_centres','clear_centres','fire_centres'])
    require(cells.fire_centres.le(cells.clear_centres).all() and cells.clear_centres.le(cells.local_centres).all(),'Invalid cell counts')
    require(all(h3.is_valid_cell(c) and h3.get_resolution(c)==8 for c in cells.cell.unique()),'Wrong spatial grid')
    grouped=cells.groupby('fire_id')[['local_centres','clear_centres','fire_centres']].sum().reindex(g.fire_id,fill_value=0)
    for a,b in [('local_centres','local_geolocated_centres'),('clear_centres','nominal_clear_centres'),('fire_centres','screened_fire_centres')]:
        require(np.array_equal(grouped[a].to_numpy(),g[b].to_numpy()),'Cell/granule count mismatch')
    meta=g.set_index('fire_id')
    for col in ['satellite','date','time_start','time_end']:require(cells[col].eq(cells.fire_id.map(meta[col])).all(),'Cell provenance mismatch')
    pd.testing.assert_frame_equal(daily,e.daily_screen_status(inv,g.to_dict('records')),check_dtype=False)
    pd.testing.assert_frame_equal(pairs,e.candidate_diagnostics(inv['time_candidates'],cells),check_dtype=False)
    # Verify observed checkpoint bytes before comparing archive counts. Raw fire-mask
    # classes match the native all-type archive scope; the stricter screen does not.
    observed=ROOT/'data/atlas/canonical_lk_2000_2024_v1';manifest=json.loads((observed/'manifest.json').read_text())
    for name,r in manifest['files'].items():
        raw=(observed/name).read_bytes();require(len(raw)==r['bytes'] and e.sha(raw)==r['sha256'],'Changed observed checkpoint')
    points=pd.read_parquet(observed/'observations.parquet');selected=points[points.acq_date.isin(e.DAYS)&points.satellite.isin(['Suomi-NPP','NOAA-20'])]
    archive_counts=selected.groupby(['acq_date','satellite']).size();agg=g.groupby(['date','satellite'])[['class_7','class_8','class_9']].sum().sum(axis=1)
    reconciliation=daily[['date','satellite','status','screened_fire_centres']].copy()
    reconciliation['archive_native_observations']=[int(archive_counts.get((d,s),0)) for d,s in zip(reconciliation.date,reconciliation.satellite)]
    reconciliation['raw_mask_fire_centres']=[int(agg[(d,s)]) if (d,s) in agg.index else None for d,s in zip(reconciliation.date,reconciliation.satellite)]
    available=reconciliation.raw_mask_fire_centres.notna();require(reconciliation.loc[available,'raw_mask_fire_centres'].eq(reconciliation.loc[available,'archive_native_observations']).all(),'Native archive/mask mismatch')
    require(reconciliation.loc[~available,'screened_fire_centres'].isna().all(),'Absent observations converted to zero')
    report={'status':'bundle_and_processed_evidence_verified','zip_name':path.name,'zip_bytes':path.stat().st_size,'zip_sha256':e.sha(path.read_bytes()),
      'manifested_members':len(members),'science_receipts':len(receipts),'science_bytes_reported':sum(r['bytes'] for r in receipts),
      'fire_granules_screened':len(g),'sparse_alignment_checked_granules':len(aligned),'sparse_alignment_max_error_degrees':float(aligned.alignment_max_error_degrees.max()),
      'zero_sparse_fire_granules_weaker_alignment':int(g.alignment_check_pixels.eq(0).sum()),'bbox_matches_with_no_local_centres':int(g.local_geolocated_centres.eq(0).sum()),
      'cell_support_rows':len(cells),'time_candidates':len(pairs),'candidates_with_common_clear_centre_cells':int(pairs.common_clear_centre_cells.gt(0).sum()),
      'available_sensor_days_reconciled':int(available.sum()),'absent_sensor_days_kept_unavailable':int((~available).sum()),
      'original_science_files_independently_reread_here':False,'receipt_limit':'Science files are retained in user cache, not this ZIP. Hash/size receipts and derived-table consistency verified; no independent local recomputation of raw science arrays.',
      'coverage_verified':False,'gap_fill_validated':False,'uncertainty_revalidated':False,'zero_months_restored':0,'frontend_changed':False,
      'daily_reconciliation':json.loads(reconciliation.to_json(orient='records'))}
    output=Path(ROOT/'data/atlas/observation_evidence_verified_v1' if output is None else output);output.mkdir(parents=True,exist_ok=True)
    for name,raw in members.items():
        target=output/'returned'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    reconciliation.to_parquet(output/'native_archive_reconciliation.parquet',index=False)
    (output/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (ROOT/'docs/atlas_observation_evidence_output_review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='daily_reconciliation'},indent=2));return report

if __name__=='__main__':run()
