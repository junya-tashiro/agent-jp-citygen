import unittest
from asset_library.subway_entrance.scripts.sign_spec import normalize_routes, parse_route_argument
class RouteInputTests(unittest.TestCase):
    def test_multiple_and_custom_color(self):
        result=normalize_routes(['M11',{'code':'AB02','color':'#123abc'}])
        self.assertEqual([r['code'] for r in result],['M11','AB02'])
        self.assertEqual(result[1]['color'],'#123ABC')
    def test_invalid_codes_colors_duplicates(self):
        for routes in (['m11'],['M1'],['M111'],['M11','M11'],[{'code':'M11','color':'red'}],'M11',['M11']*7):
            with self.subTest(routes=routes),self.assertRaises(ValueError):normalize_routes(routes)
    def test_no_routes(self):
        self.assertEqual(normalize_routes(None),[])

    def test_cli_color_and_api_equivalence(self):
        self.assertEqual(parse_route_argument('M11=#e53935'),
                         normalize_routes([{'code':'M11','color':'#E53935'}])[0])
        self.assertEqual(parse_route_argument('M11'),normalize_routes(['M11'])[0])
        for value in ('M11=','M11=red','M11=#123456=extra'):
            with self.subTest(value=value),self.assertRaises(ValueError):parse_route_argument(value)
