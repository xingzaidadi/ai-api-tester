import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.detector import ProjectDetector
from ai_api_tester.detector import ProjectInfo
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

    def test_custom_mapping_annotation_from_project_config(self):
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            source_dir = project / "src" / "main" / "java" / "com" / "example"
            source_dir.mkdir(parents=True)
            (project / ".ai-api-tester.yaml").write_text(
                "custom_mapping_annotations:\n"
                "  - InternalPostMapping\n",
                encoding="utf-8",
            )
            (source_dir / "InternalController.java").write_text(
                """
package com.example;

public class InternalController {
    @HttpApiDoc(apiName = "Internal sync")
    @InternalPostMapping(value = "/internal/sync")
    public Object sync() {
        return null;
    }
}
""",
                encoding="utf-8",
            )
            info = ProjectInfo(
                language="java",
                framework="spring-boot",
                entry_dirs=[str(project / "src" / "main" / "java")],
                file_ext="*.java",
                route_patterns=[],
            )

            routes = RouteExtractor(str(project), info).extract()
            paths = {(route.method, route.normalized_path, route.handler, route.description) for route in routes}

            self.assertIn(("POST", "/internal/sync", "sync", "Internal sync"), paths)


if __name__ == "__main__":
    unittest.main()
