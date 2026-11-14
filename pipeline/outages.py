"""Documented major interruptions; conservative monthly exclusion.

The pinned NASA inventory includes sub-day events with unresolved local impact.
The exclusion policy uses multi-day events and reviewed quality episodes. Never infer outages
from detection absence or automatically replace sensors. UTC date intervals
below flag affected months, without claiming whole days/months were offline.
"""
import pandas as pd
import json
from pathlib import Path
from functools import lru_cache

# November 2025 is omitted: FIRMS reports recovery and nominal processed data.
SOURCE='https://modaps.modaps.eosdis.nasa.gov/services/production/outages_suomi_npp.html'
MAJOR_SNPP=[('2022-07-26','2022-08-11'),('2023-07-26','2023-07-27'),
 ('2023-11-01','2023-11-02'),('2024-05-30','2024-06-04'),
 ('2024-07-09','2024-07-16'),('2024-07-24','2024-07-29'),
 ('2024-09-26','2024-09-27'),('2024-11-02','2024-11-06'),
 ('2026-03-09','2026-03-13'),
 ('2026-04-28','2026-05-01'),('2026-06-01','2026-06-03'),
 ('2026-07-10','2026-07-17'),('2026-08-03','2026-08-06')]

@lru_cache(maxsize=1)
def inventory():
    path=Path(__file__).resolve().parent.parent/'docs/outage_inventory.json'
    return json.loads(path.read_text()) if path.exists() else []

def major_outage_month(month,fam):
    month=pd.Timestamp(month)
    end=pd.Timestamp(month)+pd.offsets.MonthEnd(0)
    end=end+pd.Timedelta(days=1)
    # Terra loss affects the combined reference too; Aqua cannot be assumed to
    # replace the missing Terra cell-days. Sub-day global events remain inventoried
    # with local impact unresolved, rather than assumed to cover these regions.
    sensor='terra' if fam in ('terra','modis') else fam
    # NASA FIRMS 2026-03-30: questionable/bad until March 27 19:23Z.
    quality_episode=sensor=='terra' and month==pd.Timestamp('2026-03-01')
    events=[r for r in inventory() if r['sensor']==sensor and r['disposition']!='recovered'
            and r['duration_hours'] is not None and r['duration_hours']>=24]
    major=any(pd.Timestamp(r['start_utc']).tz_localize(None)<end and
              pd.Timestamp(r['end_utc']).tz_localize(None)>=month for r in events)
    return quality_episode or major or (fam=='snpp' and any(pd.Timestamp(a)<end and pd.Timestamp(b)>=month for a,b in MAJOR_SNPP))
