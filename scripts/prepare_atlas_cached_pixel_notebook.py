"""Build a new cache-only notebook; never overwrites the completed evidence pilot."""
from pathlib import Path
import json,hashlib,zipfile,io,base64
import pandas as pd
ROOT=Path(__file__).resolve().parent.parent
ZIP=ROOT/'cindertrace_atlas_lk_observation_evidence_20261115T001225Z.zip'
EXPECTED='e9ee5e9edf6790a31dfad88bd7e6edc7de9f681f51e76e27e3ae132699c7fe10'
assert hashlib.sha256(ZIP.read_bytes()).hexdigest()==EXPECTED
with zipfile.ZipFile(ZIP) as z:
    receipts=json.loads(z.read('bundle_manifest.json'))
    for name,receipt in receipts.items():
        raw=z.read(name);assert len(raw)==receipt['bytes'] and hashlib.sha256(raw).hexdigest()==receipt['sha256']
    inv=json.loads(z.read('catalogue/inventory.json'));downloads=json.loads(z.read('results/download_receipts.json'));boundary=z.read('catalogue/region.geojson').decode()
    previous=pd.read_parquet(io.BytesIO(z.read('results/granule_screening.parquet')))
DATA=ROOT/'data/atlas/canonical_lk_2000_2024_v1'
m=json.loads((DATA/'manifest.json').read_text())
for name,receipt in m['files'].items():
    raw=(DATA/name).read_bytes();assert len(raw)==receipt['bytes'] and hashlib.sha256(raw).hexdigest()==receipt['sha256']
p=pd.read_parquet(DATA/'observations.parquet');archive=p[p.acq_date.isin(inv['policy']['days'])&p.satellite.isin(['Suomi-NPP','NOAA-20'])][['latitude','longitude','satellite','acq_datetime','confidence','type','observation_id']].copy()
assert len(archive)==335
inputs={'prior_results_zip_sha256':EXPECTED,'observed_manifest_sha256':hashlib.sha256((DATA/'manifest.json').read_bytes()).hexdigest(),'inventory':inv,'receipts':downloads,'boundary':boundary,
 'previous_granules':json.loads(previous[['fire_id','local_geolocated_centres','nominal_clear_centres','screened_fire_centres','class_7','class_8','class_9']].to_json(orient='records')),
 'standard_observations':json.loads(archive.to_json(orient='records',date_format='iso'))}
raw=json.dumps(inputs,sort_keys=True,separators=(',',':'),allow_nan=False).encode();inputs_sha=hashlib.sha256(raw).hexdigest()
import zlib
payload=base64.b64encode(zlib.compress(raw)).decode()
base=(ROOT/'pipeline/atlas_observation_evidence.py').read_text().split("if __name__=='__main__':")[0]
audit=(ROOT/'pipeline/atlas_cached_pixel_audit.py').read_text()
cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':s.splitlines(True)})
md('''# CinderTrace — cached Sri Lanka pixel and pass audit

This continues your completed observation-evidence pilot. **No Earthdata login or new science downloads are needed.** It reads the existing `science_cache`, verifies all 68 files against the returned receipts, checks individual fire pixels and viewing geometry, and compares one-to-one satellite passes.

The verified pilot metadata and 335 corresponding standard archive observations are embedded. No input ZIP upload is needed. Keep your completed pilot notebook, original results and cache. This notebook writes a separate output folder and downloads one review ZIP. It does not change the frontend, restore missing months, fill gaps or claim complete observation coverage.''')
md('## 1. Install the readers, then restart the session\nThis may download Python packages, but makes no NASA data requests. After installation, use **Runtime → Restart session** in Colab (or restart the kernel in VS Code). Then continue from **step 2**, without rerunning this install cell. Restarting is required so loaded NumPy/SciPy components cannot mix with newly installed files. Your Drive cache is preserved.')
code('%pip -q install numpy pandas pyarrow shapely h3 scipy netCDF4\nprint("Installation finished. Restart the session/kernel now, then continue from step 2.")\n')
md('''## 2. Locate your existing cache
In Colab, the default uses the exact Drive folder from your completed pilot. It may ask for Drive access, not Earthdata login. If you moved the folder, update `PILOT_ROOT`. In VS Code, point it at the local folder containing `science_cache`. Do not point it at the small results ZIP: that ZIP intentionally excludes the science files.''')
code("from pathlib import Path\nimport sys,json,hashlib,base64,zlib,zipfile\nIN_COLAB='google.colab' in sys.modules\nif IN_COLAB:\n    from google.colab import drive\n    drive.mount('/content/drive')\n    PILOT_ROOT=Path('/content/drive/MyDrive/CinderTrace_Observation_Evidence_v1')\nelse:\n    PILOT_ROOT=Path('data/atlas/observation_evidence_run_v1')\nCACHE=PILOT_ROOT/'science_cache'\nassert CACHE.is_dir(),'Set PILOT_ROOT to the original folder containing science_cache. No download was attempted.'\nOUTPUT_ROOT=PILOT_ROOT/'pixel_pass_audit_v1'\nOUTPUT_ROOT.mkdir(parents=True,exist_ok=True)\nRESULTS=OUTPUT_ROOT/'results';RESULTS.mkdir(exist_ok=True)\nprint('Reading cache:',CACHE.resolve())\nprint('Writing new results:',RESULTS.resolve())\n")
md('## 3. Verify the embedded inputs\nThese come from your checked results ZIP and the frozen standard-data checkpoint. Type labels are carried from that archive only after a unique coordinate/time match; they are not independent confirmation of vegetation burning.')
code("INPUT_BYTES=zlib.decompress(base64.b64decode("+repr(payload)+"))\nassert hashlib.sha256(INPUT_BYTES).hexdigest()=="+repr(inputs_sha)+"\nINPUTS=json.loads(INPUT_BYTES)\nimport pandas as pd\nARCHIVE=pd.DataFrame(INPUTS['standard_observations'])\nARCHIVE['acq_datetime']=pd.to_datetime(ARCHIVE.acq_datetime,utc=True)\nPREVIOUS=pd.DataFrame(INPUTS['previous_granules'])\nassert len(ARCHIVE)==335 and len(PREVIOUS)==34\n(OUTPUT_ROOT/'verified_inputs.json').write_bytes(INPUT_BYTES)\nprint('Frozen inputs:',len(PREVIOUS),'fire granules;',len(ARCHIVE),'native standard observations.')\n")
md('''## 4. Load the method
Every local native fire pixel is checked against the fire mask and sparse arrays. Pixel quality, confidence, residual bowtie status and solar/viewing angles are retained. Archived type attribution uses a unique same-sensor coordinate match within two metres and the granule's acquisition interval; ambiguous and unmatched cases remain explicit.

Adjacent granules are grouped by sensor/date/day-night with at most a six-minute gap. Pass pairing uses each pass at most once within each 30/60/90-minute sensitivity. Mutual nearest clear pixel centres are compared at 250/500 metres with all-known, ≤40° and ≤60° viewing screens. **These are centre-proximity diagnostics, not identical physical footprints or complete area coverage.** The same data appears in several sensitivities; those are not independent samples. Granule times are not exact pixel observation times.''')
code("import types\ntry:\n    import numpy.testing\n    from scipy.spatial import cKDTree\n    from scipy.optimize import linear_sum_assignment\nexcept (ImportError,AttributeError) as error:\n    raise RuntimeError('Numerical library imports failed. Restart the Colab session (or VS Code kernel), then run steps 2 onward without rerunning the install cell. If this persists, reinstall NumPy and SciPy together and restart again. No science files were changed.') from error\nBASE_METHOD_SOURCE="+repr(base)+"\nAUDIT_METHOD_SOURCE="+repr(audit)+"\nbase_namespace={'__file__':str((OUTPUT_ROOT/'pipeline'/'base.py').resolve()),'__name__':'cached_base'}\nexec(compile(BASE_METHOD_SOURCE,'frozen_evidence_base.py','exec'),base_namespace)\naudit_namespace={'__file__':str((OUTPUT_ROOT/'pipeline'/'audit.py').resolve()),'__name__':'cached_audit','e':types.SimpleNamespace(**base_namespace)}\nexec(compile(AUDIT_METHOD_SOURCE.replace('from . import atlas_observation_evidence as e',''),'frozen_cached_pixel_audit.py','exec'),audit_namespace)\nMETHOD_HASH=hashlib.sha256((BASE_METHOD_SOURCE+AUDIT_METHOD_SOURCE+hashlib.sha256(INPUT_BYTES).hexdigest()).encode()).hexdigest()\nDERIVED=OUTPUT_ROOT/('derived_'+METHOD_HASH[:12]);DERIVED.mkdir(exist_ok=True)\n(RESULTS/'base_implementation.py').write_text(BASE_METHOD_SOURCE)\n(RESULTS/'audit_implementation.py').write_text(AUDIT_METHOD_SOURCE)\n")
md('''## 5. Reprocess and compare the cached files
The initial SHA256 check reads approximately 5 GiB from Drive; it does not download new NASA files. Reading cached files may take several minutes. Each completed granule has a derived checkpoint; reruns reuse it after checking its hashes. The derived clear-centre cache may need several hundred additional MiB. It is excluded from the final review ZIP.

Reprocessed totals must reproduce your completed pilot before being included. Any failed audit stays unavailable. Geometry changes, unknown units, missing sparse pixels or ambiguous archive matches must not be silently repaired into valid observations.''')
code("DECISION=audit_namespace['run'](\n    INPUTS['inventory'],INPUTS['receipts'],INPUTS['boundary'].encode(),ARCHIVE,PREVIOUS,\n    CACHE,RESULTS,DERIVED,METHOD_HASH)\nprint(json.dumps(DECISION,indent=2))\n")
md('''## 6. Inspect the audit
Review failures first. Native counts, stricter quality-screened counts and archive type attribution are separate fields. Each pass is used once per temporal-window sensitivity; passes can reappear across sensitivities. Zero matched centres means no shared support for that diagnostic, so fire counts on that support remain unavailable. No replacement accuracy or uncertainty score is claimed from this six-day feasibility sample.''')
code("from IPython.display import display\ndisplay(pd.DataFrame(json.loads((RESULTS/'failures.json').read_text())))\ndisplay(pd.read_parquet(RESULTS/'native_fire_pixel_audit.parquet'))\ndisplay(pd.read_parquet(RESULTS/'pass_inventory.parquet'))\ndisplay(pd.read_parquet(RESULTS/'matched_passes.parquet'))\ndisplay(pd.read_parquet(RESULTS/'unmatched_passes.parquet'))\ndisplay(pd.read_parquet(RESULTS/'mutual_centre_diagnostics.parquet'))\n")
md('''## 7. Download one review ZIP
Save this notebook with its outputs and add the ZIP to the project folder. It contains input provenance, pixel audit, pass membership and diagnostics, failures, method, runtime versions and hashes. It excludes both the original science cache and derived clear-centre cache. Keep those caches for reuse.

After this review we can freeze a seasonally balanced multi-year simulated-gap study with separate fit/calibration/evaluation periods. Six purposive days cannot validate replacement uncertainty, early historical bands, annual intervals or district allocation.''')
code(r'''from datetime import datetime,timezone
import importlib.metadata
versions={name:importlib.metadata.version(name) for name in ['numpy','pandas','pyarrow','shapely','h3','scipy','netCDF4']}
(OUTPUT_ROOT/'runtime_versions.json').write_text(json.dumps(versions,indent=2)+'\n')
archive_path=OUTPUT_ROOT/('cindertrace_atlas_lk_pixel_pass_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip')
members={'verified_inputs.json':(OUTPUT_ROOT/'verified_inputs.json').read_bytes(),'runtime_versions.json':(OUTPUT_ROOT/'runtime_versions.json').read_bytes()}
for path in sorted(RESULTS.iterdir()):
    if path.is_file():members['results/'+path.name]=path.read_bytes()
manifest={name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(members.items())}
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for name,raw in sorted(members.items()):archive.writestr(name,raw)
    archive.writestr('bundle_manifest.json',json.dumps(manifest,indent=2)+'\n')
print('Saved:',archive_path.resolve())
print('SHA256:',hashlib.sha256(archive_path.read_bytes()).hexdigest())
if IN_COLAB:
    from google.colab import files
    files.download(str(archive_path))
'''.replace("+'\\\\n'","+'\\n'"))
cells[-1]['source']=''.join(cells[-1]['source']).replace(chr(92)*2+'n',chr(92)+'n').splitlines(True)
# Code cell uses actual Python newline escapes, not newlines inside quoted strings.
for i,c in enumerate(cells):c['id']=f'cached-pixel-{i:02d}'
nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}},'nbformat':4,'nbformat_minor':5}
path=ROOT/'notebooks/CinderTrace_Atlas_LK_Cached_Pixel_Pass_Audit.ipynb';path.write_text(json.dumps(nb,indent=1)+'\n')
# Compile every ordinary cell before delivery.
import ast
for i,c in enumerate(cells):
    if c['cell_type']=='code' and not ''.join(c['source']).startswith('%pip'):ast.parse(''.join(c['source']),filename=f'cell_{i}')
print('Prepared',path.name,'with',len(cells),'cells; input SHA256',inputs_sha)
