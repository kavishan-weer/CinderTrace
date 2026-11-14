"""Reproducible inventory from pinned NASA tables; global events are not local coverage.
Run python -m pipeline.outage_inventory. Original text is retained for review.
"""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import pandas as pd
ROOT=Path(__file__).resolve().parent.parent
SOURCES={s:f'https://modaps.modaps.eosdis.nasa.gov/services/production/outages_{n}.html' for s,n in [('terra','terra'),('snpp','suomi_npp')]}

class TableRows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        if tag in ('td','th'): self.cell=''
    def handle_data(self,text):
        if self.cell is not None: self.cell+=text
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.row is not None and self.cell is not None:
            self.row.append(' '.join(self.cell.split())); self.cell=None
        if tag=='tr' and self.row:
            self.rows.append(self.row); self.row=None

def inventory():
    events=[]
    for sensor,url in SOURCES.items():
        path=ROOT/f'docs/sources/{sensor}-outages-2026-11-14.html'
        raw=path.read_bytes(); p=TableRows(); p.feed(raw.decode())
        for row in p.rows:
            if not row or not re.match(r'^\d{4}-\d{3}',row[0]): continue
            if len(row)!=5: raise ValueError(row)
            days=re.findall(r'\d{4}-\d{3}',row[0])
            start=pd.to_datetime(days[0],format='%Y-%j')+pd.Timedelta(row[2])
            end=pd.to_datetime(days[-1],format='%Y-%j')+pd.Timedelta(row[3])
            valid=end>=start
            # Preserve contradictory source timestamps without guessing a rollover.
            # A processing notice alone cannot establish whether local science data recovered.
            text=row[4].lower()
            state='recovered' if ('recovered' in text or 'no data loss' in text) else 'recovery_unverified'
            if 'unrecoverable' in text: state='unrecoverable'
            if 'delay' in text and state=='recovery_unverified': state='delay_recovery_unverified'
            events.append(dict(sensor=sensor,start_utc=start.isoformat()+'Z',end_utc=end.isoformat()+'Z',
                duration_hours=(end-start).total_seconds()/3600 if valid else None,timestamps_valid=valid,disposition=state,description=row[4],
                source=url,source_row=row,source_sha256=hashlib.sha256(raw).hexdigest(),retrieved_on='2026-11-14',
                local_observation_impact='not_established'))
    return events

def notices():
    path=ROOT/'docs/sources/firms-outages-2026-11-14.html'
    raw=path.read_bytes();p=TableRows();p.feed(raw.decode())
    rows=[]
    for row in p.rows:
        if len(row)!=2 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',row[0]):continue
        t=row[1].lower()
        state='notice_requires_review'
        if 'delay' in t or 'maintenance' in t:state='service_delay_or_maintenance'
        if 'resumed' in t or 'started' in t:state='processing_resumed_quality_unverified'
        if 'not be recoverable' in t or 'not recoverable' in t:state='unrecoverable_during_interruption'
        if 'safe' in t or 'ok to use' in t:state='quality_cleared_from_stated_time'
        if 'all processed data is now available' in t:state='processed_products_recovered'
        rows.append(dict(published_on=row[0],description=row[1],disposition=state,
            source='https://firms2.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html',
            source_sha256=hashlib.sha256(raw).hexdigest(),retrieved_on='2026-11-14',
            interpretation='Notice date is not an outage interval. Resumption does not establish recovery of prior gaps.'))
    return rows

if __name__=='__main__':
    events=inventory()
    (ROOT/'docs/outage_inventory.json').write_text(json.dumps(events,indent=2)+'\n')
    (ROOT/'docs/outage_notices.json').write_text(json.dumps(notices(),indent=2)+'\n')
    print('Inventory events:',len(events))
