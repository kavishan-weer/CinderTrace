"""Check returned cache-only audit without access to the user's raw/derived caches."""
from pathlib import Path
import ast,base64,hashlib,io,json,zlib
import numpy as np
import pandas as pd
from . import atlas_cached_pixel_audit as audit
from . import atlas_observation_evidence as e
from .verify_atlas_observation_evidence import read_verified_bundle,require,nonnegative_integers
ROOT=Path(__file__).resolve().parent.parent
ZIP=ROOT/'cindertrace_atlas_lk_pixel_pass_audit_20261115T004550Z.zip'

def run(path=None,output=None):
    path=Path(ZIP if path is None else path);members=read_verified_bundle(path);j=lambda n:json.loads(members[n]);frame=lambda n:pd.read_parquet(io.BytesIO(members['results/'+n+'.parquet']))
    inputs=j('verified_inputs.json');require(inputs['prior_results_zip_sha256']=='e9ee5e9edf6790a31dfad88bd7e6edc7de9f681f51e76e27e3ae132699c7fe10','Unexpected pilot checkpoint')
    # Verify nested result hashes and exact implementations before interpreting outputs.
    manifest=j('results/manifest.json')
    for name,r in manifest['files'].items():
        b=members['results/'+name];require(len(b)==r['bytes'] and e.sha(b)==r['sha256'],'Changed inner result')
    require(members['results/base_implementation.py']==Path(e.__file__).read_text().split("if __name__=='__main__':")[0].encode(),'Changed base method')
    require(members['results/audit_implementation.py']==Path(audit.__file__).read_bytes(),'Changed audit method')
    require(j('results/method.json')==audit.POLICY,'Changed policy');require(not j('results/failures.json'),'Audit has failures')
    # Saved notebook must carry the same inputs and method and the returned ZIP hash.
    nbpath=ROOT/'notebooks/CinderTrace_Atlas_LK_Cached_Pixel_Pass_Audit.ipynb';nb=json.loads(nbpath.read_text());errors=[];printed_hash=False;input_verified=False
    for c in nb['cells']:
        if c['cell_type']!='code':continue
        source=''.join(c['source'])
        if source.startswith('INPUT_BYTES='):
            tree=ast.parse(source);payload=ast.literal_eval(tree.body[0].value.args[0].args[0]);require(zlib.decompress(base64.b64decode(payload))==members['verified_inputs.json'],'Notebook/ZIP inputs differ');input_verified=True
        for o in c.get('outputs',[]):
            if o.get('output_type')=='error':errors.append(o.get('ename'))
            if e.sha(path.read_bytes()) in ''.join(o.get('text',[])):printed_hash=True
    require(not errors and printed_hash and input_verified,'Notebook outputs do not confirm this successful run')
    observed=ROOT/'data/atlas/canonical_lk_2000_2024_v1';om=json.loads((observed/'manifest.json').read_text());require(e.sha((observed/'manifest.json').read_bytes())==inputs['observed_manifest_sha256'],'Observed input changed')
    for name,r in om['files'].items():
        b=(observed/name).read_bytes();require(len(b)==r['bytes'] and e.sha(b)==r['sha256'],'Observed file changed')
    canonical=pd.read_parquet(observed/'observations.parquet');archive=pd.DataFrame(inputs['standard_observations']);archive['acq_datetime']=pd.to_datetime(archive.acq_datetime,utc=True)
    expected=canonical[canonical.acq_date.isin(inputs['inventory']['policy']['days'])&canonical.satellite.isin(['Suomi-NPP','NOAA-20'])][archive.columns].sort_values('observation_id').reset_index(drop=True)
    pd.testing.assert_frame_equal(archive.sort_values('observation_id').reset_index(drop=True),expected,check_dtype=False,check_exact=False,atol=1e-9,rtol=0)
    native=frame('native_fire_pixel_audit');granules=frame('granule_audit');passes=frame('pass_inventory');membership=frame('pass_membership');pairs=frame('matched_passes');unmatched=frame('unmatched_passes');d=frame('mutual_centre_diagnostics');bins=frame('view_geometry_bins')
    require(len(native)==335 and len(granules)==34,'Wrong completed pilot size');require(not native.duplicated(['fire_id','line','sample']).any(),'Duplicate native pixel')
    nonnegative_integers(native,['line','sample','confidence_class','qa']);require(native.confidence_class.isin([7,8,9]).all(),'Unexpected fire class')
    require(native.coordinate_difference_degrees.between(0,.01).all(),'Invalid grid/sparse alignment')
    nominal=native.qa_valid&((native.qa.astype('uint32')&127)==0);duplicate=(native.qa.astype('uint32')&(1<<22))!=0
    require(native.input_quality_nominal.eq(nominal).all(),'QA derivation mismatch');require(native.screened_fire.eq(nominal&~duplicate).all(),'Screen derivation mismatch')
    require(native.archive_observation_id.nunique()==335,'Archive observation reused')
    # Recompute the unique time/coordinate association, not merely its reported count.
    matched=audit.archive_match(native,archive)
    for col in ['archive_match_status','archive_observation_id','archive_type','archive_distance_metres']:
        pd.testing.assert_series_equal(matched[col],native[col],check_dtype=False,check_names=False)
    require(frame('unmatched_standard_observations').empty,'Unexpected unmatched standard observations')
    previous=pd.DataFrame(inputs['previous_granules']).set_index('fire_id');g=granules.set_index('fire_id')
    require(set(g.index)==set(previous.index),'Granule IDs differ')
    for a,b in [('local_centres','local_geolocated_centres'),('clear_centres','nominal_clear_centres'),('screened_fire_centres','screened_fire_centres')]:
        require(g[a].eq(previous.loc[g.index,b]).all(),'Previous pilot summary mismatch')
    require(g.raw_fire_centres.eq(previous.loc[g.index,['class_7','class_8','class_9']].sum(axis=1)).all(),'Raw count mismatch')
    raw=native.groupby('fire_id').size().reindex(g.index,fill_value=0);screen=native.groupby('fire_id').screened_fire.sum().reindex(g.index,fill_value=0)
    require(raw.eq(g.raw_fire_centres).all() and screen.eq(g.screened_fire_centres).all(),'Pixel/granule totals differ')
    grouped_bins=bins.groupby('fire_id')[['local_centres','clear_centres','screened_fire_centres']].sum().reindex(g.index,fill_value=0)
    require(grouped_bins.local_centres.eq(g.local_centres-g.geometry_unavailable_centres).all(),'View-bin geometry total mismatch')
    require(grouped_bins.clear_centres.le(g.clear_centres).all() and grouped_bins.screened_fire_centres.le(g.screened_fire_centres).all(),'Geometry-bin counts exceed totals')
    pd.testing.assert_frame_equal(membership,audit.group_passes(inputs['inventory']['records']),check_dtype=False)
    require(native.pass_id.eq(native.fire_id.map(membership.set_index('fire_id').pass_id)).all(),'Native pass attribution mismatch')
    require(passes.pass_id.nunique()==len(passes)==membership.pass_id.nunique(),'Pass inventory mismatch')
    for row in passes.itertuples():
        ids=membership[membership.pass_id.eq(row.pass_id)].fire_id;part=g.loc[ids]
        require(row.complete_science_screen and row.granules==len(ids),'Incomplete pass')
        require(row.local_centres==part.local_centres.sum(),'Pass centre count mismatch')
        if row.local_centres:
            require(row.native_fire_centres==part.raw_fire_centres.sum() and row.screened_fire_centres==part.screened_fire_centres.sum(),'Pass activity mismatch')
        else:require(pd.isna(row.native_fire_centres) and pd.isna(row.screened_fire_centres),'No local support converted to zero activity')
    mp=[];up=[]
    for window in [30,60,90]:
        a,b=audit.pair_passes(passes,window);mp.append(a);up.append(b)
        require(not a.snpp_pass.duplicated().any() and not a.noaa20_pass.duplicated().any(),'Pass reused within temporal window')
    pd.testing.assert_frame_equal(pairs,pd.concat(mp,ignore_index=True),check_dtype=False);pd.testing.assert_frame_equal(unmatched,pd.concat(up,ignore_index=True),check_dtype=False)
    keys=['window_minutes','snpp_pass','noaa20_pass'];require(len(d)==len(pairs)*6,'Missing pair sensitivity rows')
    require(not d.duplicated(keys+['view_cap_degrees','distance_cap_metres']).any(),'Duplicate sensitivity rows')
    require(d.merge(pairs[keys],on=keys,how='left',indicator=True)._merge.eq('both').all(),'Unknown pass diagnostic')
    nonnegative_integers(d,['snpp_eligible_clear_centres','noaa20_eligible_clear_centres','mutual_nearest_clear_centre_pairs'])
    require(d.mutual_nearest_clear_centre_pairs.le(d[['snpp_eligible_clear_centres','noaa20_eligible_clear_centres']].min(axis=1)).all(),'Reused matched centres')
    positive=d.mutual_nearest_clear_centre_pairs.gt(0)
    for col in ['snpp_fire_centres_on_support','noaa20_fire_centres_on_support']:
        require(d.loc[~positive,col].isna().all(),'No shared support forced to zero');require(d.loc[positive,col].between(0,d.loc[positive,'mutual_nearest_clear_centre_pairs']).all(),'Impossible matched activity')
    require(d.loc[positive,'median_separation_metres'].between(0,d.loc[positive,'distance_cap_metres']).all(),'Invalid distance summary')
    # Identical source-pair sensitivities repeated across time windows must agree.
    valuecols=[c for c in d.columns if c not in ['window_minutes']]
    for _,f in d.groupby(['snpp_pass','noaa20_pass','view_cap_degrees','distance_cap_metres'],dropna=False):
        require(f[valuecols].nunique(dropna=False).le(1).all(),'Repeated sensitivity results differ')
    unique_pairs=pairs.drop_duplicates(['snpp_pass','noaa20_pass']);unique=d.drop_duplicates(['snpp_pass','noaa20_pass','view_cap_degrees','distance_cap_metres'])
    report={'status':'returned_pixel_and_pass_evidence_verified','zip_name':path.name,'zip_sha256':e.sha(path.read_bytes()),'manifested_members':len(members),'science_files_reportedly_rehashed':68,
      'raw_science_independently_reread_locally':False,'clear_centre_cache_included':False,'nearest_neighbour_counts_independently_recomputed':False,
      'verification_limit':'Original/derived caches remain in user Drive; file hashes, exact method/input provenance, individual archive matches, QA, summaries and pass assignments checked; nearest-neighbour summary consistency checked without raw centre arrays.',
      'native_fire_pixels':len(native),'unique_archive_matches':335,'archive_match_max_metres':float(native.archive_distance_metres.max()),'grid_sparse_max_error_degrees':float(native.coordinate_difference_degrees.max()),
      'view_geometry_max_difference_degrees':float((native.sensor_zenith_degrees-native.sparse_view_zenith_degrees).abs().max()),'solar_geometry_max_difference_degrees':float((native.solar_zenith_degrees-native.sparse_solar_zenith_degrees).abs().max()),
      'retained_by_quality_screen':int(native.screened_fire.sum()),'screen_exclusion_counts':native.screen_exclusion_reason.value_counts().to_dict(),
      'passes':len(passes),'unique_pass_pairs':len(unique_pairs),'sensitivity_rows':len(d),'unique_sensitivity_rows':len(unique),
      'pairs_by_window':{str(k):int(v) for k,v in pairs.groupby('window_minutes').size().items()},
      'nonzero_support_sensitivities_by_view':{str(k):int(f.mutual_nearest_clear_centre_pairs.gt(0).sum()) for k,f in unique.groupby('view_cap_degrees',dropna=False)},
      'notebook_sha256':e.sha(nbpath.read_bytes()),'notebook_error_outputs':errors,'coverage_verified':False,'replacement_validated':False,'uncertainty_validated':False,'frontend_changed':False}
    output=Path(ROOT/'data/atlas/pixel_pass_verified_v1' if output is None else output);output.mkdir(parents=True,exist_ok=True)
    for name,raw in members.items():
        p=output/'returned'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    (output/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');(ROOT/'docs/atlas_pixel_pass_output_review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2));return report
if __name__=='__main__':run()
