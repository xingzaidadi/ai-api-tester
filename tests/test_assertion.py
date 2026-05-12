"""Comprehensive unit tests for AssertionEngine."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from ai_api_tester.assertion import AssertionEngine


class TestAssertStatus(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_status_pass(self):
        self.assertTrue(self.engine.assert_status(200, 200))
        self.assertEqual(len(self.engine.results), 0)

    def test_status_fail(self):
        self.assertFalse(self.engine.assert_status(404, 200))
        self.assertEqual(len(self.engine.results), 1)
        self.assertEqual(self.engine.results[0].field, "status")


class TestAssertResponseTime(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_response_time_pass(self):
        self.assertTrue(self.engine.assert_response_time(100, 500))
        self.assertEqual(len(self.engine.results), 0)

    def test_response_time_fail_exceeds(self):
        self.assertFalse(self.engine.assert_response_time(600, 500))
        self.assertEqual(len(self.engine.results), 1)

    def test_response_time_fail_equal(self):
        # Equal to max is a failure (strict less-than)
        self.assertFalse(self.engine.assert_response_time(500, 500))
        self.assertEqual(len(self.engine.results), 1)


class TestAssertHeaders(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_headers_literal_pass(self):
        headers = {"Content-Type": "application/json", "X-Request-Id": "abc123"}
        expects = {"Content-Type": "application/json"}
        self.assertTrue(self.engine.assert_headers(headers, expects))
        self.assertEqual(len(self.engine.results), 0)

    def test_headers_literal_fail(self):
        headers = {"Content-Type": "text/html"}
        expects = {"Content-Type": "application/json"}
        self.assertFalse(self.engine.assert_headers(headers, expects))
        self.assertEqual(len(self.engine.results), 1)

    def test_headers_smart_assertion(self):
        headers = {"X-Request-Id": "req-12345"}
        expects = {"X-Request-Id": "@notNull"}
        self.assertTrue(self.engine.assert_headers(headers, expects))

    def test_headers_missing_key(self):
        headers = {}
        expects = {"X-Missing": "@notNull"}
        self.assertFalse(self.engine.assert_headers(headers, expects))
        self.assertEqual(len(self.engine.results), 1)


class TestAssertBodyNestedPaths(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_nested_dot_path(self):
        body = {"data": {"user": {"name": "Alice"}}}
        self.assertTrue(self.engine.assert_body(body, {"data.user.name": "Alice"}))
        self.assertEqual(len(self.engine.results), 0)

    def test_nested_dot_path_fail(self):
        body = {"data": {"user": {"name": "Bob"}}}
        self.assertFalse(self.engine.assert_body(body, {"data.user.name": "Alice"}))
        self.assertEqual(len(self.engine.results), 1)

    def test_array_index_path(self):
        body = {"data": {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}}
        self.assertTrue(self.engine.assert_body(body, {"data.items.0.id": 1}))

    def test_array_index_path_second_element(self):
        body = {"data": {"items": [{"id": 10}, {"id": 20}]}}
        self.assertTrue(self.engine.assert_body(body, {"data.items.1.id": 20}))

    def test_missing_nested_key_returns_none(self):
        body = {"data": {}}
        self.assertFalse(self.engine.assert_body(body, {"data.user.name": "Alice"}))

    def test_multiple_expects(self):
        body = {"status": "ok", "count": 5}
        result = self.engine.assert_body(body, {"status": "ok", "count": 5})
        self.assertTrue(result)
        self.assertEqual(len(self.engine.results), 0)


class TestSmartAssertionNotNull(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_not_null_pass(self):
        body = {"name": "Alice"}
        self.assertTrue(self.engine.assert_body(body, {"name": "@notNull"}))

    def test_not_null_fail(self):
        body = {"name": None}
        self.assertFalse(self.engine.assert_body(body, {"name": "@notNull"}))


class TestSmartAssertionIsNull(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_is_null_pass(self):
        body = {"deleted_at": None}
        self.assertTrue(self.engine.assert_body(body, {"deleted_at": "@isNull"}))

    def test_is_null_fail(self):
        body = {"deleted_at": "2024-01-01"}
        self.assertFalse(self.engine.assert_body(body, {"deleted_at": "@isNull"}))


class TestSmartAssertionComparisons(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_gt_pass(self):
        body = {"score": 90}
        self.assertTrue(self.engine.assert_body(body, {"score": "@gt(80)"}))

    def test_gt_fail_equal(self):
        body = {"score": 80}
        self.assertFalse(self.engine.assert_body(body, {"score": "@gt(80)"}))

    def test_gt_fail_less(self):
        body = {"score": 70}
        self.assertFalse(self.engine.assert_body(body, {"score": "@gt(80)"}))

    def test_gte_pass_equal(self):
        body = {"score": 80}
        self.assertTrue(self.engine.assert_body(body, {"score": "@gte(80)"}))

    def test_gte_pass_greater(self):
        body = {"score": 81}
        self.assertTrue(self.engine.assert_body(body, {"score": "@gte(80)"}))

    def test_gte_fail(self):
        body = {"score": 79}
        self.assertFalse(self.engine.assert_body(body, {"score": "@gte(80)"}))

    def test_lt_pass(self):
        body = {"latency": 50}
        self.assertTrue(self.engine.assert_body(body, {"latency": "@lt(100)"}))

    def test_lt_fail_equal(self):
        body = {"latency": 100}
        self.assertFalse(self.engine.assert_body(body, {"latency": "@lt(100)"}))

    def test_lte_pass_equal(self):
        body = {"latency": 100}
        self.assertTrue(self.engine.assert_body(body, {"latency": "@lte(100)"}))

    def test_lte_fail(self):
        body = {"latency": 101}
        self.assertFalse(self.engine.assert_body(body, {"latency": "@lte(100)"}))


class TestSmartAssertionIn(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_in_pass(self):
        body = {"role": "admin"}
        self.assertTrue(self.engine.assert_body(body, {"role": '@in(["admin","user"])'}))

    def test_in_fail(self):
        body = {"role": "guest"}
        self.assertFalse(self.engine.assert_body(body, {"role": '@in(["admin","user"])'}))


class TestSmartAssertionNotEqual(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_not_equal_pass(self):
        body = {"status": "active"}
        self.assertTrue(self.engine.assert_body(body, {"status": "@notEqual(deleted)"}))

    def test_not_equal_fail(self):
        body = {"status": "deleted"}
        self.assertFalse(self.engine.assert_body(body, {"status": "@notEqual(deleted)"}))


class TestSmartAssertionContains(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_contains_pass(self):
        body = {"message": "Hello World"}
        self.assertTrue(self.engine.assert_body(body, {"message": "@contains('World')"}))

    def test_contains_fail(self):
        body = {"message": "Hello World"}
        self.assertFalse(self.engine.assert_body(body, {"message": "@contains('Goodbye')"}))

    def test_contains_non_string_actual_fail(self):
        body = {"count": 42}
        self.assertFalse(self.engine.assert_body(body, {"count": "@contains('4')"}))


class TestSmartAssertionNotContains(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_not_contains_pass(self):
        body = {"message": "Success"}
        self.assertTrue(self.engine.assert_body(body, {"message": "@not_contains('error')"}))

    def test_not_contains_fail(self):
        body = {"message": "An Error occurred"}
        self.assertFalse(self.engine.assert_body(body, {"message": "@not_contains('error')"}))


class TestSmartAssertionMatches(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_matches_pass(self):
        body = {"email": "user@example.com"}
        self.assertTrue(self.engine.assert_body(body, {"email": r"@matches(.+@.+\..+)"}))

    def test_matches_fail(self):
        body = {"email": "not-an-email"}
        self.assertFalse(self.engine.assert_body(body, {"email": r"@matches(^\d+$)"}))


class TestSmartAssertionStartsEndsWith(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_starts_with_pass(self):
        body = {"url": "https://example.com"}
        self.assertTrue(self.engine.assert_body(body, {"url": "@startsWith('https')"}))

    def test_starts_with_fail(self):
        body = {"url": "http://example.com"}
        self.assertFalse(self.engine.assert_body(body, {"url": "@startsWith('https')"}))

    def test_ends_with_pass(self):
        body = {"filename": "report.pdf"}
        self.assertTrue(self.engine.assert_body(body, {"filename": "@endsWith('.pdf')"}))

    def test_ends_with_fail(self):
        body = {"filename": "report.doc"}
        self.assertFalse(self.engine.assert_body(body, {"filename": "@endsWith('.pdf')"}))


class TestSmartAssertionSize(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_size_pass(self):
        body = {"tags": ["a", "b", "c"]}
        self.assertTrue(self.engine.assert_body(body, {"tags": "@size(3)"}))

    def test_size_fail(self):
        body = {"tags": ["a", "b"]}
        self.assertFalse(self.engine.assert_body(body, {"tags": "@size(3)"}))

    def test_min_size_pass(self):
        body = {"items": [1, 2, 3]}
        self.assertTrue(self.engine.assert_body(body, {"items": "@minSize(2)"}))

    def test_min_size_fail(self):
        body = {"items": [1]}
        self.assertFalse(self.engine.assert_body(body, {"items": "@minSize(2)"}))

    def test_max_size_pass(self):
        body = {"items": [1, 2]}
        self.assertTrue(self.engine.assert_body(body, {"items": "@maxSize(3)"}))

    def test_max_size_fail(self):
        body = {"items": [1, 2, 3, 4]}
        self.assertFalse(self.engine.assert_body(body, {"items": "@maxSize(3)"}))


class TestSmartAssertionTypeChecks(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_is_string_pass(self):
        body = {"name": "Alice"}
        self.assertTrue(self.engine.assert_body(body, {"name": "@isString"}))

    def test_is_string_fail(self):
        body = {"name": 123}
        self.assertFalse(self.engine.assert_body(body, {"name": "@isString"}))

    def test_is_number_pass(self):
        body = {"age": 25}
        self.assertTrue(self.engine.assert_body(body, {"age": "@isNumber"}))

    def test_is_number_pass_float(self):
        body = {"score": 3.14}
        self.assertTrue(self.engine.assert_body(body, {"score": "@isNumber"}))

    def test_is_number_fail(self):
        body = {"age": "twenty-five"}
        self.assertFalse(self.engine.assert_body(body, {"age": "@isNumber"}))

    def test_is_array_pass(self):
        body = {"items": [1, 2, 3]}
        self.assertTrue(self.engine.assert_body(body, {"items": "@isArray"}))

    def test_is_array_fail(self):
        body = {"items": "not a list"}
        self.assertFalse(self.engine.assert_body(body, {"items": "@isArray"}))


class TestBodyLevelNotContains(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_body_not_contains_list_pass(self):
        body = {"message": "All good", "status": "ok"}
        self.assertTrue(self.engine.assert_body(body, {"@not_contains": ["error", "sql"]}))

    def test_body_not_contains_list_fail(self):
        body = {"message": "SQL syntax error near..."}
        self.assertFalse(self.engine.assert_body(body, {"@not_contains": ["error", "sql"]}))

    def test_body_not_contains_string_pass(self):
        body = {"message": "Success"}
        self.assertTrue(self.engine.assert_body(body, {"@not_contains": "failure"}))

    def test_body_not_contains_string_fail(self):
        body = {"message": "A Failure happened"}
        self.assertFalse(self.engine.assert_body(body, {"@not_contains": "failure"}))


class TestUnknownAssertion(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_unknown_assertion_produces_failure(self):
        body = {"field": "value"}
        self.assertFalse(self.engine.assert_body(body, {"field": "@bogusAssertion"}))
        self.assertEqual(len(self.engine.results), 1)
        self.assertIn("unknown assertion", self.engine.results[0].expected)


class TestLiteralValueMatching(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_literal_string_match(self):
        body = {"status": "ok"}
        self.assertTrue(self.engine.assert_body(body, {"status": "ok"}))

    def test_literal_int_match(self):
        body = {"count": 42}
        self.assertTrue(self.engine.assert_body(body, {"count": 42}))

    def test_literal_mismatch(self):
        body = {"status": "error"}
        self.assertFalse(self.engine.assert_body(body, {"status": "ok"}))
        self.assertEqual(len(self.engine.results), 1)


class TestResultsAccumulate(unittest.TestCase):
    def setUp(self):
        self.engine = AssertionEngine()

    def test_multiple_failures_accumulate(self):
        self.engine.assert_status(404, 200)
        self.engine.assert_response_time(1000, 500)
        self.engine.assert_body({"x": 1}, {"x": 2})
        self.assertEqual(len(self.engine.results), 3)


if __name__ == "__main__":
    unittest.main()
