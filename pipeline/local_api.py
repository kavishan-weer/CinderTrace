"""Local-only area analytics and raw-point exports. No remote data is fetched.
Started by web/scripts/dev.mjs; binds only to loopback on an OS-assigned port.
"""
import argparse
import json
import math
import pathlib
import re
import secrets
import signal
import shutil
import tempfile
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import duckdb
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Point, box, shape
from shapely.prepared import prep

from .analytics import load_region, selected_monthly
from .export_web import COLS, records, export_columns
from .grid import H3_RESOLUTION
from .regions import REGIONS

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATS = {'veg', 'volcano', 'static', 'offshore'}


@lru_cache(maxsize=3)
def dataset(region):
    return load_region(region)


def region_name(request):
    region = request.get('region')
    if region not in REGIONS:
        raise ValueError('Choose Sri Lanka, California, or New South Wales.')
    return region


def selection_geometry(request, region):
    polygon = request.get('polygon')
    if polygon is None:
        return None
    if not isinstance(polygon, dict) or polygon.get('type') != 'Polygon':
        raise ValueError('Draw a polygon with at least three distinct vertices.')
    rings = polygon.get('coordinates', [])
    if not isinstance(rings, list) or not rings or sum(len(r) for r in rings) > 501:
        raise ValueError('Use a polygon with at most 500 vertices.')
    for ring in rings:
        for coordinate in ring:
            if len(coordinate) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in coordinate):
                raise ValueError('Polygon coordinates must be finite longitude/latitude pairs.')
            if not (-180 <= coordinate[0] <= 180 and -85 <= coordinate[1] <= 85):
                raise ValueError('Keep coordinates within longitude ±180° and latitude ±85°.')
    geometry = shape(polygon)
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError('The polygon crosses itself or has no area. Redraw its boundary.')
    if geometry.bounds[2] - geometry.bounds[0] > 180:
        raise ValueError('Selections crossing the date line are not supported.')
    if not geometry.intersects(box(*REGIONS[region]['bbox'])):
        raise ValueError('The area is outside the selected region. Change region or choose an overlapping area.')
    return geometry


def area_result(request):
    region = region_name(request)
    geometry = selection_geometry(request, region)
    if geometry is None:
        raise ValueError('Provide a polygon or coordinate area.')
    cells, monthly, members = dataset(region)
    zone = prep(geometry)
    selected = members[[zone.covers(Point(lon, lat)) for lon, lat in zip(members.lon, members.lat)]]
    if selected.empty:
        out = monthly.copy()
        for col in ['harmonized', 'lo', 'hi', 'modis_raw', 'viirs_snpp_raw']:
            out[col] = np.nan
        out['source'] = 'missing'
        out['period_status'] = 'missing'
        out['comparison_eligible'] = False
        out['slice_status'] = 'unavailable'
        out['interval_status'] = 'unavailable'
    else:
        out = selected_monthly(cells, monthly, members, cell_ids=selected.h3_cell.tolist())
    return {'rows': records(out[export_columns(out)]), 'cell_ids': selected.h3_cell.tolist(),
            'cell_count': len(selected), 'grid_area_km2': float(selected.area_km2.sum()),
            'selection_method': 'H3 cell centres; raw CSV uses exact point coordinates'}


def month_range(request):
    start, end = request.get('start'), request.get('end')
    if not all(isinstance(x, str) and re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', x) for x in [start, end]):
        raise ValueError('Choose valid start and end months.')
    if start > end or start < '2000-01' or end > '2100-12':
        raise ValueError('Choose an ordered date window from 2000 onward.')
    return pd.Timestamp(start + '-01'), pd.Timestamp(end + '-01') + pd.offsets.MonthBegin(1)


def export_hotspots(request, output):
    region = region_name(request)
    geometry = selection_geometry(request, region)
    start, stop = month_range(request)
    cats, confs = request.get('cats'), request.get('confs')
    if not isinstance(cats, list) or not cats or any(c not in CATS for c in cats):
        raise ValueError('Select at least one valid activity category.')
    if not isinstance(confs, list) or not confs or any(type(c) is not int or c not in [1, 2, 3] for c in confs):
        raise ValueError('Select at least one valid confidence level.')
    cells, _, members = dataset(region)
    sub = request.get('sub')
    if geometry is not None and sub is not None:
        raise ValueError('Choose a polygon or administrative area, not both.')
    if sub is not None:
        if type(sub) is not int:
            raise ValueError('Invalid administrative area.')
        definitions = json.loads((ROOT/f'data/boundaries/{region}_subs.geojson').read_text())['features']
        if sub not in {f['properties']['id'] for f in definitions}:
            raise ValueError('Invalid administrative area.')
        members = members[members['sub'] == sub]
    labels = cells[['h3_cell', 'cat']].drop_duplicates()
    metadata = members[['h3_cell', 'sub']].merge(labels, on='h3_cell', validate='one_to_one')
    files = [str(path) for year in range(start.year, stop.year + 1)
             if (path := ROOT/f'data/raw/{region}/{year}.parquet').exists()]
    if not files:
        raise ValueError('No local archive files exist for this date window.')
    # Categorization/threshold selection is shared with the aggregate pipeline.
    # Confidence is assigned across the full regional sensor-family cell-day,
    # before the exact point clip, so all selected detections stay original rows.
    with duckdb.connect() as con:
        con.register('metadata', metadata)
        con.create_function('to_h3', lambda lat, lon: h3.latlng_to_cell(lat, lon, H3_RESOLUTION), ['DOUBLE', 'DOUBLE'], 'VARCHAR')
        zone = prep(geometry) if geometry is not None else None
        con.create_function('in_area', lambda lon, lat: zone.covers(Point(lon, lat)) if zone else True, ['DOUBLE', 'DOUBLE'], 'BOOLEAN')
        query = """
        WITH tagged AS (
          SELECT r.*, m.h3_cell, m.sub, m.cat AS category,
            CASE WHEN sensor='MODIS' THEN 'modis' ELSE satellite END AS confidence_family,
            CASE WHEN sensor='MODIS' THEN CASE WHEN confidence_pct<30 THEN 1 WHEN confidence_pct<80 THEN 2 ELSE 3 END
                 ELSE CASE confidence WHEN 'l' THEN 1 WHEN 'n' THEN 2 WHEN 'h' THEN 3 ELSE 2 END END AS display_confidence
          FROM read_parquet(?) r JOIN metadata m ON to_h3(r.lat,r.lon)=m.h3_cell
          WHERE acq_date>=? AND acq_date<?
        ), scored AS (
          SELECT *, max(display_confidence) OVER (PARTITION BY h3_cell,acq_date,confidence_family) AS cell_day_confidence
          FROM tagged
        )
        SELECT * EXCLUDE(confidence_family), 'original satellite detection; not harmonized' AS record_kind,
               ? AS spatial_selection
        FROM scored WHERE category IN (SELECT unnest(?))
          AND cell_day_confidence IN (SELECT unnest(?)) AND in_area(lon,lat)
        """
        method = 'exact_polygon_point_clip_within_regional_archive' if zone else 'regional_H3_membership' if sub is None else 'administrative_H3_membership'
        count = con.execute('COPY (' + query + ') TO ? (FORMAT CSV, HEADER TRUE)',
                            [files, start.date(), stop.date(), method, cats, confs, str(output)]).fetchone()[0]
    return int(count)


class Server(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    exports = {}
    exports_lock = threading.Lock()
    jobs = threading.BoundedSemaphore(2)
    export_root = None

    def log_message(self, *_):
        pass

    def respond(self, status, payload):
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # The local service is reachable only through loopback. Reject foreign
        # browser origins; no CORS permission is granted to arbitrary websites.
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).hostname not in ['127.0.0.1', 'localhost', '::1']:
            return self.respond(403, {'error': 'Use the local CINDERTRACE app.'})
        if not self.jobs.acquire(blocking=False):
            return self.respond(429, {'error': 'Two local queries are already running. Try again shortly.'})
        output = None
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 100_000:
                raise ValueError('The selected area is too large to process.')
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError('Invalid selection.')
            if self.path == '/api/area':
                return self.respond(200, area_result(request))
            if self.path == '/api/events/query':
                from .event_api import query_events
                region=region_name(request)
                return self.respond(200,query_events(request,selection_geometry(request,region)))
            if self.path == '/api/events/detail':
                from .event_api import event_detail
                return self.respond(200,event_detail(request))
            if self.path not in ['/api/exports/hotspots', '/api/exports/brief']:
                return self.respond(404, {'error': 'Unknown local query.'})
            with self.exports_lock:
                for token, (path, expiry, _) in list(self.exports.items()):
                    if expiry < time.time():
                        path.unlink(missing_ok=True)
                        del self.exports[token]
            token = secrets.token_urlsafe(24)
            is_pdf = self.path == '/api/exports/brief'
            output = pathlib.Path(self.export_root)/f"{token}.{'pdf' if is_pdf else 'csv'}"
            if is_pdf:
                from .brief_pdf import render_brief
                count = render_brief(request.get('brief'), output)
                filename = f"cindertrace-situation-brief-{request['brief']['selected']}.pdf"
            else:
                count = export_hotspots(request, output)
                filename = f"cindertrace-{request['region']}-raw-hotspots-{request['start']}-{request['end']}.csv"
            with self.exports_lock:
                self.exports[token] = (output, time.time() + 600, filename)
            self.respond(200, {'url': f"/api/exports/{token}.{'pdf' if is_pdf else 'csv'}", 'pages' if is_pdf else 'rows': count, 'bytes': output.stat().st_size, 'filename': filename})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            if output:
                output.unlink(missing_ok=True)
            self.respond(422, {'error': str(error)})
        except ImportError:
            if output:
                output.unlink(missing_ok=True)
            self.respond(500, {'error': 'PDF support is missing. Install the repository Python requirements and restart the local app.'})
        except Exception:
            if output:
                output.unlink(missing_ok=True)
            self.respond(500, {'error': 'The local export or archive query failed. Restart the local app and retry.'})
        finally:
            self.jobs.release()

    def do_GET(self):
        if self.path == '/api/health':
            return self.respond(200, {'status': 'ready', 'mode': 'local-only'})
        match = re.fullmatch(r'/api/exports/([A-Za-z0-9_-]{32})\.(csv|pdf)', self.path)
        if not match:
            return self.respond(404, {'error': 'Unknown local download.'})
        token, extension = match.groups()
        with self.exports_lock:
            item = self.exports.get(token)
        if not item or item[1] < time.time() or item[0].suffix != f'.{extension}':
            return self.respond(404, {'error': 'This download expired. Generate it again.'})
        path, _, filename = item
        self.send_response(200)
        self.send_header('Content-Type', 'application/pdf' if extension == 'pdf' else 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(path.stat().st_size))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                shutil.copyfileobj(stream, self.wfile, length=1024*1024)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cindertrace-exports-') as directory:
        Handler.export_root = directory
        server = Server(('127.0.0.1', args.port), Handler)
        print(json.dumps({'api_url': f'http://127.0.0.1:{server.server_port}'}), flush=True)
        def interrupt(*_):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGINT, interrupt)
        def clean_expired():
            while True:
                time.sleep(60)
                with Handler.exports_lock:
                    for token, (path, expiry, _) in list(Handler.exports.items()):
                        if expiry < time.time():
                            path.unlink(missing_ok=True)
                            del Handler.exports[token]
        threading.Thread(target=clean_expired, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

if __name__ == '__main__':
    main()
