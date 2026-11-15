"""Build the full resumable validation notebook without modifying executed pilots."""
from pathlib import Path
import ast,base64,hashlib,json,zlib
import pandas as pd
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'notebooks/CinderTrace_Atlas_LK_Multiyear_Validation.ipynb'
if OUT.exists():
    previous=json.loads(OUT.read_text())
    if any(c.get('execution_count') is not None or c.get('outputs') for c in previous['cells']):raise RuntimeError('Executed notebook exists; preserve it and choose a new output filename.')
base=ROOT/'data/atlas/canonical_lk_2000_2024_v1';observed=json.loads((base/'manifest.json').read_text())
for name,r in observed['files'].items():
    b=(base/name).read_bytes();assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
metadata=ROOT/'data/atlas/viirs_expansion_inventory_v1';manifest=json.loads((metadata/'manifest.json').read_text())
for name,r in manifest['files'].items():
    b=(metadata/name).read_bytes();assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
design=json.loads((ROOT/'docs/atlas_viirs_expansion_design_v1.json').read_text());inventory=json.loads((metadata/'inventory.json').read_text())
assert inventory['design_sha256']==hashlib.sha256((ROOT/'docs/atlas_viirs_expansion_design_v1.json').read_bytes()).hexdigest()
p=pd.read_parquet(base/'observations.parquet');selected=p[p.acq_date.isin([r['date'] for r in design['dates']])&p.satellite.isin(['Suomi-NPP','NOAA-20'])][['latitude','longitude','satellite','acq_datetime','confidence','type','observation_id']]
inputs={'design':design,'inventory':inventory,'boundary':(base/'region.geojson').read_text(),'standard_observations':json.loads(selected.to_json(orient='records',date_format='iso')),
 'observed_manifest_sha256':hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest(),'inventory_summary':manifest,
 'source_metadata_files':{name:(metadata/name).read_text() for name in manifest['files'] if name.startswith('cmr/')}}
raw=json.dumps(inputs,sort_keys=True,separators=(',',':'),allow_nan=False).encode();input_sha=hashlib.sha256(raw).hexdigest();payload=base64.b64encode(zlib.compress(raw)).decode()
BASE=(ROOT/'pipeline/atlas_observation_evidence.py').read_text().split("if __name__=='__main__':")[0]
PIXEL=(ROOT/'pipeline/atlas_cached_pixel_audit.py').read_text();STUDY=(ROOT/'pipeline/atlas_multiyear_validation.py').read_text()
cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)})
md('''# CinderTrace — Sri Lanka multi-year observed-activity validation

This notebook runs the frozen **54-date, 2018–2024** study in three resumable batches, followed by one results download. Public catalogue records, original metadata pages, source hashes and standard archive observations are embedded. No input upload or FIRMS key is needed. Earthdata login is required for new science downloads.

**Read the resource note:** the linked fire/geolocation files total approximately **45.6 GiB of downloads**. Processing stages one granule's new raw files at a time in temporary storage, then removes only those temporary copies after checkpointing. Original pilot caches are preserved. Derived clear-centre evidence and receipts stay in Drive for resuming; allow several GiB of additional Drive space and at least a couple of GiB of temporary working space. Actual space/time depends on the files and service. A runtime interruption can require re-downloading the current incomplete granule, but completed derived checkpoints are reused.

The two unresolved early NOAA-20 dates (2018-04-19 and 2018-05-27) are explicitly unavailable when the fire product is absent. The notebook does not invent files or substitute a different sensor/version. They remain in status tables, and are excluded from affected training comparisons.

This is regional research on observed activity, not a production data release. It does not modify the frontend, fill actual gaps, restore zero months or validate early-history/annual uncertainty.''')
md('''## 1. Install, then restart
Run this cell once. Then select **Runtime → Restart session** in Colab, or restart the VS Code kernel. Continue at **step 2**, without rerunning installation. This avoids mixing already-loaded NumPy/SciPy libraries with newly installed files. Drive data is preserved.''')
code('%pip -q install numpy pandas pyarrow shapely h3 scipy netCDF4 earthaccess\nprint("Restart the session/kernel now, then continue from step 2.")\n')
md('## 2. Check the numerical environment\nIf this fails, restart first and rerun from here. Do not patch private NumPy functions.')
code('''import sys,json,hashlib,base64,zlib,zipfile,types
from pathlib import Path
try:
    import numpy as np
    import numpy.testing
    import pandas as pd
    from scipy.spatial import cKDTree
    from scipy.optimize import nnls,linear_sum_assignment
    from netCDF4 import Dataset
    import h3
except (ImportError,AttributeError) as error:
    raise RuntimeError('Numerical imports failed. Restart the session/kernel after installation, then resume from step 2.') from error
print('Numerical imports passed. Python:',sys.version.split()[0])
''')
md('''## 3. Set persistent and temporary storage
In Colab, the defaults use your existing pilot folder and a new study folder in Drive. `SCRATCH` is temporary runtime storage for new raw files; it is separate from the preserved pilot cache. In VS Code, update `PILOT_ROOT` and `STUDY_ROOT` if needed. Do not put `SCRATCH` inside an existing source cache. The notebook never deletes files from `ORIGINAL_CACHE`.''')
code('''import tempfile
IN_COLAB='google.colab' in sys.modules
if IN_COLAB:
    from google.colab import drive
    drive.mount('/content/drive')
    PILOT_ROOT=Path('/content/drive/MyDrive/CinderTrace_Observation_Evidence_v1')
    STUDY_ROOT=Path('/content/drive/MyDrive/CinderTrace_Multiyear_Validation_v1')
    SCRATCH=Path('/content/cindertrace_multiyear_temporary_raw')
else:
    PILOT_ROOT=Path('data/atlas/observation_evidence_run_v1')
    STUDY_ROOT=Path('data/atlas/multiyear_validation_run_v1')
    SCRATCH=Path(tempfile.gettempdir())/'cindertrace_multiyear_temporary_raw'
ORIGINAL_CACHE=PILOT_ROOT/'science_cache'
STUDY_ROOT.mkdir(parents=True,exist_ok=True);SCRATCH.mkdir(parents=True,exist_ok=True)
assert not SCRATCH.resolve().is_relative_to(ORIGINAL_CACHE.resolve()),'Choose a separate scratch directory.'
print('Study workspace:',STUDY_ROOT.resolve())
print('Temporary raw staging:',SCRATCH.resolve())
print('Preserved optional source cache:',ORIGINAL_CACHE.resolve())
''')
md('''## 4. Verify the frozen inputs
Fit dates are in 2018–2020, calibration in 2021–2022 and evaluation in 2023–2024. Dates were selected using calendar strata and availability, without ranking fire counts. The first quarter of 2018 has no eligible NOAA-20 archive dates and remains unsupported. Exact source pages and hashes are retained. Earlier aggregate scores and pilot evidence have already been inspected; this is not a blind external replication.''')
code("INPUT_BYTES=zlib.decompress(base64.b64decode("+repr(payload)+"))\nassert hashlib.sha256(INPUT_BYTES).hexdigest()=="+repr(input_sha)+"\nINPUTS=json.loads(INPUT_BYTES)\nassert len(INPUTS['design']['dates'])==54\nassert hashlib.sha256(INPUTS['boundary'].encode()).hexdigest()=='838db6bf67cb4d21df585d32483c64c9d56556d4fc216564bf4aa982c659382e'\nfor name,text in INPUTS['source_metadata_files'].items():\n    receipt=INPUTS['inventory_summary']['files'][name]\n    assert len(text.encode())==receipt['bytes'] and hashlib.sha256(text.encode()).hexdigest()==receipt['sha256'],name\n(STUDY_ROOT/'verified_inputs.json').write_bytes(INPUT_BYTES)\nprint('Dates:',INPUTS['design']['date_counts_by_partition'])\nprint('Linked catalogue volume GiB:',round(INPUTS['inventory_summary']['matched_download_catalogue_gib'],2))\nprint('Unresolved dates:',INPUTS['inventory_summary']['early_dates_needing_source_reconciliation'])\n")
md('''## 5. Load the frozen processing and evaluation methods
Per-granule checkpoints preserve native pixels, QA, coordinate/type matching, viewing geometry, clear-centre evidence and download receipts. Native archive reconciliation must succeed before vegetation counts are available. Completed date checkpoints are hashed and checked on reruns.

**Two separate analyses:** shared-support diagnostics evaluate every temporal candidate before assigning geometry-admissible one-to-one pass pairs. They never select by fire counts. The simulated-outage predictor receives **only NOAA-20 screened vegetation active cells and calendar month**. It cannot use S-NPP masks, geometry or shared-support selection, which would be unavailable during a real outage.

The target is S-NPP-observed, quality-screened vegetation active-cell-days on the fixed regional H3 resolution-8 grid. Type labels are carried from the standard archive, not independently confirmed burning type. Zero requires archive reconciliation and some nominal-clear support; missing products, failed processing and absent clear support remain unavailable. This target differs from raw pixel counts and complete fire activity.

Model selection uses fit-year holdouts only, with a global ratio, shrunk seasonal ratio or nonnegative affine model. Calibration is separate. Exploratory 80/90% date intervals require at least twelve supported calibration dates. Sensitivity rows and pixels are not independent evaluation samples. There are no nominal coverage guarantees under temporal dependence, and no monthly or annual interval claims.''')
code("BASE_SOURCE="+repr(BASE)+"\nPIXEL_SOURCE="+repr(PIXEL)+"\nSTUDY_SOURCE="+repr(STUDY)+"\nbase_ns={'__file__':str((STUDY_ROOT/'pipeline'/'base.py').resolve()),'__name__':'study_base'}\nexec(compile(BASE_SOURCE,'frozen_base.py','exec'),base_ns)\nE=types.SimpleNamespace(**base_ns)\npixel_ns={'__file__':str((STUDY_ROOT/'pipeline'/'pixel.py').resolve()),'__name__':'study_pixel','e':E}\nexec(compile(PIXEL_SOURCE.replace('from . import atlas_observation_evidence as e',''),'frozen_pixel.py','exec'),pixel_ns)\nP=types.SimpleNamespace(**pixel_ns)\nstudy_ns={'__file__':str((STUDY_ROOT/'pipeline'/'study.py').resolve()),'__name__':'study_validation','e':E,'p':P}\nstandalone=STUDY_SOURCE.replace('from . import atlas_observation_evidence as e','').replace('from . import atlas_cached_pixel_audit as p','')\nexec(compile(standalone,'frozen_multiyear_validation.py','exec'),study_ns)\nMETHOD_HASH=hashlib.sha256((BASE_SOURCE+PIXEL_SOURCE+STUDY_SOURCE+hashlib.sha256(INPUT_BYTES).hexdigest()).encode()).hexdigest()\nWORK=STUDY_ROOT/('run_'+METHOD_HASH[:12]);WORK.mkdir(exist_ok=True)\nRESULTS=WORK/'results';RESULTS.mkdir(exist_ok=True)\nfor name,source in [('base_implementation.py',BASE_SOURCE),('pixel_implementation.py',PIXEL_SOURCE),('study_implementation.py',STUDY_SOURCE)]:\n    (RESULTS/name).write_text(source)\nprint('Resumable run:',WORK.resolve())\n")
md('''## 6. Sign in to Earthdata
Enter credentials only at the interactive prompts. Login is not persisted or included in outputs. LP DAAC and LAADS access are both needed. If a batch reports an access denial, rerun this login cell and that same batch cell; successful granules are reused. Later batch cells skip work while `SESSION_READY` is false. Do not share credentials or authenticated redirect URLs.''')
code("import earthaccess\nauth=earthaccess.login(strategy='interactive',persist=False)\nassert auth.authenticated,'Complete Earthdata login before continuing.'\nsession=earthaccess.get_requests_https_session()\nSESSION_READY=True\nprint('Authenticated for this kernel. No login is written into the research output.')\n")
for number,title,years in [(7,'Fit batch: 2018–2020',[2018,2019,2020]),(8,'Calibration batch: 2021–2022',[2021,2022]),(9,'Evaluation batch: 2023–2024',[2023,2024])]:
    md(f'## {number}. {title}\nRun this batch and inspect its final status. You can resume the notebook later by repeating setup/login and this cell. Keep the frozen dates and method unchanged. New raw copies are staged temporarily; completed derived checkpoints stay in Drive.')
    code("if SESSION_READY:\n    batch=study_ns['run_batch'](INPUTS,"+repr(years)+",session,ORIGINAL_CACHE,SCRATCH,WORK,METHOD_HASH)\n    print(json.dumps(batch,indent=2))\n    if batch['access_denied']:\n        SESSION_READY=False\n        print('Access denied: rerun step 6, then this batch cell. Verified checkpoints are retained.')\nelse:\n    print('Batch skipped: rerun the Earthdata login cell, then this batch.')\n")
md('''## 10. Build the final evidence tables and run the frozen evaluation
This can also package an honest partial run. Every planned date gets an explicit availability/status row. The two unresolved NOAA-20 dates remain unavailable and do not become zero activity. Models are withheld if fit support is insufficient; intervals are withheld if calibration support is insufficient. Only reference-available evaluation dates are scored. The source predictor's output is not selected using reference availability.

Actual-outage distribution shifts, local observing coverage, early-history transfer and district allocation remain unvalidated. No actual gaps are filled, regardless of these exploratory scores.''')
code("DECISION=study_ns['finalize'](INPUTS,WORK,RESULTS,METHOD_HASH)\nprint(json.dumps(DECISION,indent=2))\nfrom IPython.display import display\ndisplay(pd.read_parquet(RESULTS/'date_status.parquet'))\ndisplay(pd.read_parquet(RESULTS/'noaa20_features.parquet'))\ndisplay(pd.read_parquet(RESULTS/'evaluation_metrics.parquet'))\ndisplay(pd.DataFrame(json.loads((RESULTS/'failures.json').read_text())))\n")
md('''## 11. Download one results ZIP
Run this after finalization, even for a partial run. Save this notebook with its outputs and add the ZIP to the project folder. It includes the frozen inputs and original catalogue evidence, native pixel audit, pass diagnostics, source-only features, separate reference labels, held-out predictions, calibration bounds, split/model audit, failure states, receipts, methods, versions and hashes. Raw and derived clear-centre caches are excluded. Keep the Drive study workspace for resuming or reviewing centres. Your original frontend remains unchanged.''')
code(r'''from datetime import datetime,timezone
import importlib.metadata
assert study_ns['checkpoint_valid'](RESULTS,'manifest.json',{'method_hash':METHOD_HASH}),'Finalize results before downloading.'
versions={name:importlib.metadata.version(name) for name in ['numpy','pandas','pyarrow','shapely','h3','scipy','netCDF4','earthaccess']}
members={'verified_inputs.json':INPUT_BYTES,'runtime_versions.json':(json.dumps(versions,indent=2)+'\n').encode()}
for path in sorted(RESULTS.iterdir()):
    if path.is_file():members['results/'+path.name]=path.read_bytes()
manifest={name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(members.items())}
archive_path=WORK/('cindertrace_atlas_lk_multiyear_validation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip')
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for name,raw in sorted(members.items()):archive.writestr(name,raw)
    archive.writestr('bundle_manifest.json',json.dumps(manifest,indent=2)+'\n')
print('Saved:',archive_path.resolve())
print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
if 'session' in globals():session.close()
if IN_COLAB:
    from google.colab import files
    files.download(str(archive_path))
''')
cells[-1]['source']=''.join(cells[-1]['source']).replace(chr(92)*2+'n',chr(92)+'n').splitlines(True)
for i,c in enumerate(cells):
    c['id']=f'multiyear-{i:02d}'
    if c['cell_type']=='code' and not ''.join(c['source']).startswith('%pip'):ast.parse(''.join(c['source']),filename=f'cell{i}')
nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}},'nbformat':4,'nbformat_minor':5}
OUT.write_text(json.dumps(nb,indent=1)+'\n')
print('Prepared',OUT.name,'cells',len(cells),'embedded standard observations',len(selected),'input bytes',len(raw),'SHA256',input_sha)
