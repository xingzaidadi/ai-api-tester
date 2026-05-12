import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.detector import ProjectDetector
from ai_api_tester.route_extractor import RouteExtractor


class RouteExtractorTest(unittest.TestCase):
    def _routes(self, fixture_name):
        project = ROOT / "tests" / "fixtures" / fixture_name
        info = ProjectDetector(str(project)).detect()
        return RouteExtractor(str(project), info).extract()

    def test_spring_combines_class_prefix_and_method_path(self):
        routes = self._routes("spring-basic")
        paths = {(route.method, route.normalized_path, route.handler) for route in routes}
        self.assertIn(("POST", "/api/v1/orders", "createOrder"), paths)
        self.assertIn(("GET", "/api/v1/orders/{param}", "getOrder"), paths)

    def test_fastapi_combines_include_router_and_router_prefix(self):
        routes = self._routes("fastapi-basic")
        paths = {(route.method, route.normalized_path, route.handler) for route in routes}
        self.assertIn(("POST", "/api/v1/orders", "create_order"), paths)
        self.assertIn(("GET", "/api/v1/orders/{param}", "get_order"), paths)

    def test_matches_path_parameters(self):
        project = ROOT / "tests" / "fixtures" / "spring-basic"
        info = ProjectDetector(str(project)).detect()
        matches = RouteExtractor(str(project), info).find_matches("/api/v1/orders/123", "GET")
        self.assertEqual("getOrder", matches[0].handler)

    def test_filters_method(self):
        project = ROOT / "tests" / "fixtures" / "spring-basic"
        info = ProjectDetector(str(project)).detect()
        matches = RouteExtractor(str(project), info).find_matches("/api/v1/orders", "GET")
        self.assertEqual([], matches)


if __name__ == "__main__":
    unittest.main()
