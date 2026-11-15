"""Create a continuation notebook without overwriting executed history evidence."""
from pathlib import Path
import copy,json
ROOT=Path(__file__).resolve().parent.parent
source=ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb'
original=json.loads(source.read_text());cells=[]
for cell in original['cells']:
    c=copy.deepcopy(cell);text=''.join(c['source'])
    if c['cell_type']=='markdown' and text.startswith('## 6.'):break
    if c['cell_type']=='code':c['outputs']=[];c['execution_count']=None
    cells.append(c)
cells[0]['source']='''# CinderTrace — earlier Sri Lanka history: all batches, one download

Run this notebook in order, or use **Runtime → Run all**. It covers **2000–2021** in separate three-year cells, then downloads **one combined ZIP** at the end. There is no manual handoff between batches.

Your existing 2000–2002 run is reused. Keep `NEW_RUN=False` and the same Drive folder/active run. Completed years are checksum-checked and skipped; interrupted requests resume from cache. No benchmark or frontend files are changed.

The data helpers and pinned run contract below are copied unchanged from the executed notebook so existing cached years remain compatible. Only orchestration and download packaging are added.

Enter your existing FIRMS MAP_KEY at the hidden prompt. No Earthdata password is needed. Network/quota failures stop rather than becoming zeros; resolve the service issue and rerun the failed batch cell. All later batch cells are independently named and safe to rerun.

**Cells:** 2000–2002; 2003–2005; 2006–2008; 2009–2011; 2012–2014; 2015–2017; 2018–2020; 2021. The last cell packages all completed year ZIPs, their hashes and shared evidence into one download. It refuses to label an incomplete history as complete.

For a one-time download of only the work already finished, run setup/helper cells through the batch/download helper definition, then call `download_history_bundle(require_all=False)` in a new cell. This makes one clearly labelled partial ZIP without downloading any more data.

The original executed notebook and results remain intact. Source availability, NRT separation, unknown coverage, partial-month totals and the early Aqua rule are unchanged. No calibration or scientific validation scores are produced.
'''.splitlines(keepends=True)
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(keepends=True)})
def code(s):cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':s.splitlines(keepends=True)})
md('## Batch and single-download functions\nEach batch skips completed years. The download function verifies saved files and year ZIP hashes before creating one combined archive. It never zips the entire Drive folder or includes incomplete-year files.\n')
helper='\n'.join(line for line in (ROOT/'pipeline/atlas_history_bundle.py').read_text().splitlines() if not line.startswith('from .'))+'\n'
code(helper)
code('''def run_history_batch(years):
    return run_fixed_history_batch(OUT,years,HISTORY_YEARS,process_year,package_year)

def download_history_bundle(require_all=True,download=True):
    result=collect_history_bundle(OUT,HISTORY_YEARS,package_year,BENCHMARK_REFERENCE,require_all=require_all)
    print('ONE FILE:',result['path'])
    print('Completed years:',result['manifest']['completed_years'])
    print('Remaining years:',result['manifest']['remaining_years'])
    print('SHA256:',result['sha256'])
    print('Size:',round(result['bytes']/1024**2,2),'MiB')
    if download:
        if IN_COLAB:
            from google.colab import files
            files.download(str(result['path']))
        else:
            from IPython.display import FileLink
            display(FileLink(str(result['path'])))
    return result
''')
batches=[list(range(a,min(a+3,2022))) for a in range(2000,2022,3)]
for i,years in enumerate(batches,1):
    label=str(years[0]) if len(years)==1 else f'{years[0]}–{years[-1]}'
    md(f'## Batch {i}: {label}\nRun this cell in order. Completed years reuse their verified files and make no data requests.\n')
    code(f'batch_{i}_receipts=run_history_batch({years!r})\n')
md('## Download once\nThis cell requires all 2000–2021 year captures to be complete. Save the executed notebook and return this single combined ZIP for independent verification. Observing coverage and cross-sensor calibration remain unverified.\n')
code('FINAL_BUNDLE=download_history_bundle()\n')
for i,c in enumerate(cells):c['id']=f'atlas-all-batches-{i:02}'
nb={'cells':cells,'metadata':copy.deepcopy(original['metadata']),'nbformat':4,'nbformat_minor':5}
nb['metadata']['colab']={'name':'CinderTrace_Atlas_LK_History_2000_2021_All_Batches.ipynb'}
path=ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_All_Batches.ipynb';path.write_text(json.dumps(nb,indent=1)+'\n');print(path)
