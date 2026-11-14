"""Rebuild monthly/browser outputs after correctness fixes, preserving old outputs.
Existing raw and cell archives are not rewritten; old research is historical only.
"""
import json
import shutil
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from . import harmonize
from .analytics import export_subregions

def run():
    root=harmonize.ROOT
    backup=root/'data/audit_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True,exist_ok=False)
    for region in ['lk','ca','nsw']:
        for suffix in ['monthly.parquet','sub_monthly.parquet','coverage.parquet','report.json']:
            source=root/f'data/harmonized/{region}_{suffix}'
            if source.exists():shutil.copy2(source,backup/source.name)
    results=[]
    for region in ['lk','ca','nsw']:
        with patch.object(harmonize,'build_cells',side_effect=lambda r:pd.read_parquet(root/f'data/harmonized/{r}_cells.parquet')):
            report,_,monthly=harmonize.run(region)
        export_subregions(region)
        assert monthly.groupby('month').size().eq(12).all()
        assert not monthly.duplicated(['month','cat','conf']).any()
        coverage=pd.read_parquet(root/f'data/harmonized/{region}_coverage.parquet')
        flagged=coverage[(coverage.fam=='snpp')&coverage.known_major_outage]
        assert not flagged.status.eq('inferred_available').any()
        results.append({'region':region,'monthly_rows':len(monthly),'flagged_reference_months':int(len(flagged)),
            'eligible_month_slices':int(monthly.comparison_eligible.sum())})
        print(region,results[-1],flush=True)
    from .export_web import run as export
    export()
    (backup/'repair-result.json').write_text(json.dumps(results,indent=2))
    print('Previous monthly outputs preserved:',backup)

if __name__=='__main__':run()
