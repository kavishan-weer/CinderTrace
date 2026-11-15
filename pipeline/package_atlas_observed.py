"""Create one analysis-input archive from the isolated verified observed checkpoint."""
from pathlib import Path
import json,zipfile
from .import_atlas_pilot import ROOT
from .atlas_history import digest

def package_checkpoint(folder,verification_path,policy_path,destination):
    folder=Path(folder);destination=Path(destination)
    if destination.resolve().is_relative_to(folder.resolve()):raise ValueError('Archive must be outside the dataset directory')
    manifest_raw=(folder/'manifest.json').read_bytes();m=json.loads(manifest_raw)
    if m['coverage_verified'] is not False or m['harmonization_validated'] is not False or m['production_export_enabled'] is not False:raise ValueError('Unexpected scientific or release claims')
    entries={}
    for name,r in m['files'].items():
        if Path(name).name!=name or name.startswith('.'):raise ValueError('Unexpected dataset filename')
        raw=(folder/name).read_bytes()
        if len(raw)!=r['bytes'] or digest(raw)!=r['sha256']:raise ValueError('Dataset file hash/size differs')
        entries[name]=raw
    entries['dataset_manifest.json']=manifest_raw
    entries['history_verification.json']=Path(verification_path).read_bytes()
    entries['benchmark_source_policy.json']=Path(policy_path).read_bytes()
    index={'archive_type':'observed_standard_analysis_inputs','dataset_id':m['dataset_id'],'observations':m['observations'],
      'coverage_verified':False,'harmonization_validated':False,'production_export_enabled':False,
      'note':'Verified source consistency; no certification of complete observing coverage or physical fire truth. Raw source archives remain separate and are identified by checkpoint hashes.',
      'files':{name:{'bytes':len(raw),'sha256':digest(raw)} for name,raw in entries.items()}}
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(str(destination)+'.part')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in entries.items():archive.writestr(name,raw)
        archive.writestr('analysis_bundle_manifest.json',json.dumps(index,indent=2))
    temporary.replace(destination)
    return {'path':str(destination),'bytes':destination.stat().st_size,'sha256':digest(destination.read_bytes()),'manifest':index}

if __name__=='__main__':
    r=package_checkpoint(ROOT/'data/atlas/canonical_lk_2000_2024_v1',ROOT/'docs/atlas_history_2000_2021_verification.json',ROOT/'docs/atlas_observed_source_policy.json',ROOT/'data/atlas/cindertrace_atlas_lk_observed_2000_2024_v1.zip')
    (ROOT/'docs/atlas_observed_analysis_bundle.json').write_text(json.dumps({k:v for k,v in r.items() if k!='manifest'},indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='manifest'},indent=2))
