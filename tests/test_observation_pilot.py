import unittest
from unittest.mock import patch
from shapely.geometry import box
from pipeline.observation_pilot import intersects,probe_access,StopLoginRedirect,LoginRequired

class ObservationPilotTests(unittest.TestCase):
    def test_metadata_footprint_uses_latitude_longitude_order(self):
        e={'polygons':[['5 79 10 79 10 82 5 82 5 79']]}
        self.assertTrue(intersects(e,box(80,6,81,9)))
        self.assertFalse(intersects(e,box(30,6,31,9)))
        self.assertIsNone(intersects({},box(80,6,81,9)))

    def test_earthdata_redirect_is_identified_before_following_login(self):
        with self.assertRaises(LoginRequired):
            StopLoginRedirect().redirect_request(None,None,302,'',{},'https://urs.earthdata.nasa.gov/oauth/authorize?client_id=example')

    def test_html_success_does_not_establish_science_file_access(self):
        class Response:
            status=200
            headers={'Content-Type':'text/html'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'<html>Sign in</html>'
        with patch('pipeline.observation_pilot.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value=Response()
            self.assertEqual(probe_access('https://example.org/data.hdf')['status'],'unexpected_response')
