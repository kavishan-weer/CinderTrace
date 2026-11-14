import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from shapely.geometry import Polygon,Point,box,mapping

from ml.assess_incidents import annotate_links,match_indices,merge_review,project_local,read_case,score_case
from ml.events import EARTH_KM
from ml.incident_references import decode_rings


class IncidentAssessmentTests(unittest.TestCase):
    def test_reference_support_flags_do_not_conflate_minor_and_material_associations(self):
        links=pd.DataFrame([{'case_id':'a','event_id':'x','reference_points':10},{'case_id':'a','event_id':'y','reference_points':2},{'case_id':'b','event_id':'x','reference_points':5}])
        scores=pd.DataFrame([{'case_id':'a','case_kind':'incident','material_fragments':1,'material_min_points':3},{'case_id':'b','case_kind':'official_complex','material_fragments':1,'material_min_points':3}])
        result=annotate_links(links,scores)
        self.assertEqual(result.shared_candidate_review.tolist(),[True,False,True])
        self.assertEqual(result.material_reference_association.tolist(),[True,False,True])
        self.assertTrue(result.association_note.str.contains('not an official incident').all())

    def test_native_ring_decoder_preserves_holes_and_islands_in_any_ring_order(self):
        shell=[(0,0),(0,4),(4,4),(4,0),(0,0)]
        hole=[(1,1),(3,1),(3,3),(1,3),(1,1)]
        island=[(1.5,1.5),(1.5,2.5),(2.5,2.5),(2.5,1.5),(1.5,1.5)]
        geometry,notes=decode_rings([island,hole,shell])
        self.assertAlmostEqual(geometry.area,13)
        self.assertTrue(geometry.covers(Point(2,2)))
        self.assertFalse(geometry.covers(Point(1.2,1.2)))
        self.assertEqual(notes['interior_rings'],1)
        self.assertTrue(geometry.equals(decode_rings([shell,hole,island])[0]))
        with self.assertRaises(ValueError):decode_rings([hole])

    def test_exact_matching_keeps_boundary_excludes_holes_and_uses_explicit_dates(self):
        polygon=Polygon([(80,8),(80.1,8),(80.1,8.1),(80,8.1)],holes=[[(80.04,8.04),(80.06,8.04),(80.06,8.06),(80.04,8.06)]])
        start=pd.Timestamp('2020-01-02T00:00Z');end=start
        data=pd.DataFrame({'lon':[80,80.05,80.02,80.02,80.02], 'lat':[8,8.05,8.02,8.02,8.02],
            'acq_datetime':pd.to_datetime(['2020-01-02T00:00Z','2020-01-02T00:00Z','2020-01-01T00:00Z','2020-01-04T00:00Z','2020-01-03T23:59Z'])})
        self.assertEqual(match_indices(data,polygon,start,end).tolist(),[0,2,4])
        self.assertEqual(match_indices(data,polygon,start,end,date_padding_days=0).tolist(),[0])

    def test_one_km_buffer_is_metric_and_does_not_admit_distant_points(self):
        data=pd.DataFrame({'lon':[79.995,79.98],'lat':[8.005,8.005],'acq_datetime':pd.to_datetime(['2020-01-02T12:00Z']*2)})
        start=pd.Timestamp('2020-01-02T00:00Z');polygon=box(80,8,80.01,8.01)
        self.assertEqual(match_indices(data,polygon,start,start).tolist(),[])
        self.assertEqual(match_indices(data,polygon,start,start,buffer_km=1).tolist(),[0])
        for lat in [0,40,-34]:
            lon=1/(EARTH_KM*np.cos(np.radians(lat)))*180/np.pi
            x,y=project_local(np.array([lon]),np.array([lat]),0,lat)
            self.assertAlmostEqual(float(np.hypot(x,y)[0]),1,places=5)

    def test_fragment_statistics_distinguish_matched_points_from_global_components(self):
        labels=np.array([0]*80+[1]*15+[2]*4+[3]+[0]*100)
        case={'id':'a','name':'Incident A','kind':'incident'}
        result,material=score_case(case,np.arange(100),labels,np.bincount(labels))
        self.assertEqual(result['candidate_fragments'],4)
        self.assertEqual(result['material_fragments'],3)
        self.assertEqual(result['dominant_reference_share'],.8)
        self.assertAlmostEqual(result['dominant_candidate_reference_fraction'],80/180)
        self.assertEqual(result['global_singletons'],1)
        self.assertEqual(material,{0:80,1:15,2:4})
        empty,_=score_case(case,np.array([],dtype=int),labels,np.bincount(labels))
        self.assertIsNone(empty['dominant_reference_share'])

    def test_shared_candidates_are_review_flags_with_reference_overlap_exposed(self):
        cases=[{'id':'a','geometry':box(0,0,1,1)},{'id':'b','geometry':box(2,0,3,1)}]
        result=merge_review(cases,{'a':np.array([0,1,2]),'b':np.array([3,4,5])},{'a':{7:3},'b':{7:3}})
        self.assertEqual(len(result),1);self.assertFalse(result[0]['reference_polygons_overlap']);self.assertEqual(result[0]['points_associated_with_both_references'],0)
        self.assertEqual(merge_review(cases,{'a':np.array([0]),'b':np.array([1])},{'a':{7:3},'b':{8:3}}),[])

    def test_reference_provenance_and_missing_dates_are_enforced(self):
        case={'id':'test','source':'agency','name':'Test','where':'id=1'}
        sources={'agency':{'id_field':'id','start_field':'start','end_field':'end','date_meaning':'dates'}}
        with tempfile.TemporaryDirectory() as directory,patch('ml.assess_incidents.CACHE',Path(directory)):
            root=Path(directory);path=root/'test.geojson';meta=root/'test.provenance.json'
            data={'features':[{'properties':{'id':1,'start':1577923200000,'end':1578009600000},'geometry':mapping(box(80,8,81,9))}]}
            path.write_text(json.dumps(data));record={'case':case,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'query_url':'https://example.org/query'};meta.write_text(json.dumps(record))
            self.assertEqual(read_case(case,sources)['agency_identifier'],'1')
            path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'SHA-256'):read_case(case,sources)
            data['features'][0]['properties']['end']=None;path.write_text(json.dumps(data));record['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();meta.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'missing agency dates'):read_case(case,sources)


if __name__=='__main__':unittest.main()
