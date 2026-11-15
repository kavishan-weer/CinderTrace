"""Operational batching and single-download packaging; does not change data contracts."""
from pathlib import Path
import json,zipfile
from .atlas_history import verify_year_files,digest

def verified_year_zip(out,year,package_year):
    out=Path(out);contract_path=out/'run_contract.json';contract=json.loads(contract_path.read_text());run_id=contract['run_id']
    folder=out/'years'/str(year);m=verify_year_files(folder)
    if m['year']!=year or m['run_contract_sha256']!=digest(contract_path.read_bytes()):raise ValueError('Completed year belongs to a different run contract')
    expected_name=f'cindertrace_atlas_lk_history_{year}_{run_id}.zip';receipt_path=out/f'year_{year}_zip_receipt.json';path=out/expected_name
    if receipt_path.exists() and path.exists():
        r=json.loads(receipt_path.read_text())
        if r['zip_name']!=expected_name or r['year']!=year or r['canonical_standard_rows']!=m['canonical_standard_rows']:raise ValueError('Year ZIP receipt contract differs')
        raw=path.read_bytes()
        if len(raw)!=r['bytes'] or digest(raw)!=r['sha256']:raise ValueError('Saved year ZIP changed; preserve it for review')
        return r
    r=package_year(folder)
    if r['zip_name']!=expected_name:raise ValueError('Packager returned an unexpected year ZIP name')
    return verified_year_zip(out,year,package_year)

def run_fixed_history_batch(out,years,target_years,process_year,package_year):
    years=list(years);target_years=list(target_years)
    if not years or len(years)>3 or len(set(years))!=len(years) or any(y not in target_years for y in years):raise ValueError('Batch must contain up to three distinct target history years')
    receipts=[]
    for year in years:
        folder=Path(out)/'years'/str(year)
        if (folder/'year_manifest.json').is_file():
            r=verified_year_zip(out,year,package_year)
            print(f'{year}: reused completed evidence; no downloads.')
        else:
            process_year(year)
            r=verified_year_zip(out,year,package_year)
            print(f'{year}: completed and saved.')
        receipts.append(r)
    return receipts

def collect_history_bundle(out,target_years,package_year,benchmark_reference,require_all=True):
    """Create one ZIP of verified year ZIPs and evidence index; partial capture stays explicit."""
    out=Path(out);target_years=list(target_years)
    if len(set(target_years))!=len(target_years) or not target_years or any(y<2000 or y>2021 for y in target_years):raise ValueError('Invalid target history years')
    contract_path=out/'run_contract.json';contract=json.loads(contract_path.read_text());run_id=contract['run_id']
    if contract['target_years']!=target_years:raise ValueError('Bundle target differs from the pinned run')
    completed=[y for y in target_years if (out/'years'/str(y)/'year_manifest.json').is_file()]
    remaining=[y for y in target_years if y not in completed]
    if require_all and remaining:raise ValueError(f'History is incomplete; missing years: {remaining}. Run the remaining batch cells, or use require_all=False for an explicitly partial download.')
    if not completed:raise ValueError('No completed year evidence is available to download')
    receipts=[verified_year_zip(out,y,package_year) for y in completed]
    progress={'run_id':run_id,'target_years':target_years,'completed_years':completed,'remaining_years':remaining,
      'capture_status':'all_target_years_captured' if not remaining else 'partial_capture',
      'year_zip_receipts':receipts,'benchmark_reference':benchmark_reference,'run_contract_sha256':digest(contract_path.read_bytes()),
      'coverage_verified':False,'harmonization_applied':False,'frontend_changed':False}
    entries={}
    for r in receipts:entries['year_zips/'+r['zip_name']]=out/r['zip_name']
    shared=['run_contract.json','region.geojson','official_history_plan.parquet','documented_global_gaps.parquet','upstream_missing_standard_dates.parquet','unparsed_outage_evidence.parquet']
    for name in shared:
        if not (out/name).is_file():raise ValueError(f'Missing shared evidence file: {name}')
        entries['shared/'+name]=out/name
    for path in sorted((out/'snapshots').iterdir()):
        if path.is_file():entries['shared/snapshots/'+path.name]=path
    progress_raw=json.dumps(progress,indent=2,allow_nan=False).encode()
    index={**progress,'files':{}}
    for name,path in entries.items():
        raw=path.read_bytes();index['files'][name]={'bytes':len(raw),'sha256':digest(raw)}
    index['files']['progress.json']={'bytes':len(progress_raw),'sha256':digest(progress_raw)}
    label='complete_2000_2021' if not remaining else 'partial_completed_years'
    destination=out/f'cindertrace_atlas_lk_history_{label}_{run_id}.zip';temporary=Path(str(destination)+'.part')
    # Year ZIPs are already compressed. Store them to avoid repeatedly compressing the same data.
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED) as archive:
        for name,path in entries.items():archive.write(path,name)
        archive.writestr('progress.json',progress_raw)
        archive.writestr('bundle_manifest.json',json.dumps(index,indent=2,allow_nan=False))
    temporary.replace(destination)
    (out/'progress.json').write_bytes(progress_raw)
    return {'path':destination,'sha256':digest(destination.read_bytes()),'bytes':destination.stat().st_size,'manifest':index}
