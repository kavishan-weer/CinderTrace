import copy
import re
import tempfile
import unittest
import json
import http.client
import threading
from pathlib import Path

from pipeline.brief_pdf import render_brief, validate_brief


def snapshot():
    return {
        'version': 1, 'area': 'Sri Lanka / 8.000, 80.500 / 25 km radius',
        'filters': 'Vegetation / Nominal + High', 'snapshot': '2026-11-13',
        'window': '2013-2026', 'spatial': '48 H3 centres / regional calibration',
        'selected': '2026-09', 'selected_label': 'Sep 2026',
        'generated_utc': '2026-11-13T00:00:00Z', 'year_basis': 'January-December',
        'status': 'Comparable archive month',
        'cards': [dict(label=key, value=value, note='Selected-area monthly activity') for key,value in [('Activity','54'),('Median','51.7'),('Percentile','52 / 100')]],
        'findings': ['Selected month has 54 cell-days.', 'Latest season lasts 4 months.', 'No significance claim is made.'],
        'calendar': [dict(label=str(year),months=[dict(month=f'{year}-{i+1:02}',value=None if i==11 else i,eligible=i!=11,provisional=i==10) for i in range(12)]) for year in range(2019,2027)],
        'profile': dict(label='2025',keys=[f'2025-{i+1:02}' for i in range(12)],values=[0,0,10,30,30,20,10,0,0,0,0,0],onset=2,end=5,duration=4,peaks=[3,4],total=100,low_data=False),
        'limits': ['Transfer range is not total measurement uncertainty.', 'Availability is inferred, not verified coverage.', 'Local calibration has not been independently validated.'],
        'coverage': 'Calendar shows the latest 8 starting years. Prior same-month comparisons use the full archive.',
        'sources': 'NASA FIRMS / geoBoundaries / archive snapshot',
    }


class BriefPDFTests(unittest.TestCase):
    def test_vector_pdf_is_one_page_with_or_without_season(self):
        with tempfile.TemporaryDirectory() as directory:
            for profile in [snapshot()['profile'], None]:
                brief = snapshot(); brief['profile'] = profile
                output = Path(directory)/'brief.pdf'
                self.assertEqual(render_brief(brief,output),1)
                content = output.read_bytes()
                self.assertTrue(content.startswith(b'%PDF-'))
                self.assertEqual(len(re.findall(rb'/Type\s*/Page\b',content)),1)
                self.assertGreater(len(content),3000)

    def test_missing_and_malformed_payloads_are_rejected_before_rendering(self):
        bad_cases = [None, {}, {**snapshot(),'selected':'2026-99'}, {**snapshot(),'findings':['x']*4}, {**snapshot(),'calendar':[]}]
        nonfinite=snapshot(); nonfinite['calendar'][0]['months'][0]['value']=float('inf');bad_cases.append(nonfinite)
        malformed=snapshot();malformed['profile']['duration']=12;bad_cases.append(malformed)
        for payload in bad_cases:
            with self.assertRaises(ValueError):validate_brief(payload)

    def test_long_area_and_all_uncertainty_notes_still_fit_one_page(self):
        brief=copy.deepcopy(snapshot())
        brief['area']='New South Wales / Selected coordinate area / 250 km radius / region-clipped custom polygon'
        brief['filters']='Vegetation, Industrial, Volcanic, Offshore / confidence Low + Nominal + High'
        brief['spatial']='Polygon extent: lon 145.000 to 153.000, lat -36.000 to -28.000 / 14,000 H3 centres / 500,000 km2 grid area.'
        brief['limits']=[
            'Selected-month transfer range: 1,000.5-22,000.5 cell-days. This is a model-transfer range, not a total measurement confidence interval.',
            'Availability is inferred from regional archive activity, not verified satellite overpasses or cloud-free coverage. Provisional and missing months cannot establish low fire risk.',
            'H3 cell-centre selection and regional calibration apply. Local transfer accuracy and uncertainty have not been independently validated. Source classes and confidence levels are heuristic conventions.',
            'Season onset/end use cumulative 10%/90% activity; duration is an inclusive monthly window, which may contain quiet intervals. Fire-active cell-days are not individual fires, burned area or a forecast.',
            'Low-data calibration is present in this selection; interpret timing and activity with additional caution.',
        ]
        with tempfile.TemporaryDirectory() as directory:self.assertEqual(render_brief(brief,Path(directory)/'long.pdf'),1)


class BriefDownloadTests(unittest.TestCase):
    def setUp(self):
        from pipeline.local_api import Handler, Server
        self.handler=Handler
        self.tmp=tempfile.TemporaryDirectory()
        self.old_root,self.old_exports=Handler.export_root,Handler.exports
        Handler.export_root=self.tmp.name;Handler.exports={}
        self.server=Server(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.handler.export_root,self.handler.exports=self.old_root,self.old_exports
        self.tmp.cleanup()

    def request(self,method,path,body=None,origin='http://127.0.0.1:5173'):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request(method,path,body=json.dumps(body) if body else None,headers={'Origin':origin,'Content-Type':'application/json'})
        response=connection.getresponse();result=(response.status,dict(response.getheaders()),response.read());connection.close();return result

    def test_pdf_creation_and_streaming_with_correct_type_and_expiry(self):
        status,_,body=self.request('POST','/api/exports/brief',{'brief':snapshot()})
        self.assertEqual(status,200);meta=json.loads(body);self.assertEqual(meta['pages'],1)
        status,headers,content=self.request('GET',meta['url'])
        self.assertEqual(status,200);self.assertEqual(headers['Content-Type'],'application/pdf');self.assertTrue(content.startswith(b'%PDF-'))
        self.assertIn('attachment;',headers['Content-Disposition'])
        self.assertEqual(self.request('GET',meta['url'].replace('.pdf','.csv'))[0],404)
        token=meta['url'].split('/')[-1][:-4];path,_,filename=self.handler.exports[token];self.handler.exports[token]=(path,0,filename)
        self.assertEqual(self.request('GET',meta['url'])[0],404)

    def test_malformed_brief_and_foreign_browser_origin_are_rejected(self):
        self.assertEqual(self.request('POST','/api/exports/brief',{'brief':None})[0],422)
        self.assertEqual(self.request('POST','/api/exports/brief',{'brief':snapshot()},origin='https://example.com')[0],403)
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[])


if __name__=='__main__':unittest.main()
