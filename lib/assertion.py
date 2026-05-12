"""
智能断言引擎：支持 @notNull、@gt、@contains 等语义化断言
"""

import re
import json
from typing import Any


class AssertionError_(Exception):
    def __init__(self, field: str, expected: str, actual: Any):
        self.field = field
        self.expected = expected
        self.actual = actual
        super().__init__(f"[{field}] expected {expected}, got {repr(actual)}")


class AssertionEngine:
    def __init__(self):
        self.results = []

    def assert_status(self, actual: int, expected: int) -> bool:
        if actual != expected:
            self.results.append(AssertionError_("status", str(expected), actual))
            return False
        return True

    def assert_body(self, body: dict, expects: dict, prefix: str = "body") -> bool:
        all_pass = True
        for key, expected in expects.items():
            if key.startswith("@"):
                all_pass &= self._assert_body_level(body, key, expected)
                continue

            actual = self._get_nested(body, key)
            if not self._check_assertion(f"{prefix}.{key}", expected, actual):
                all_pass = False
        return all_pass

    def assert_headers(self, headers: dict, expects: dict) -> bool:
        all_pass = True
        for key, expected in expects.items():
            actual = headers.get(key)
            if not self._check_assertion(f"headers.{key}", expected, actual):
                all_pass = False
        return all_pass

    def _assert_body_level(self, body: Any, directive: str, value: Any) -> bool:
        if directive == "@not_contains":
            body_str = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
            if isinstance(value, list):
                for v in value:
                    if v.lower() in body_str.lower():
                        self.results.append(AssertionError_("body", f"not contains '{v}'", f"found '{v}' in response"))
                        return False
            elif isinstance(value, str):
                if value.lower() in body_str.lower():
                    self.results.append(AssertionError_("body", f"not contains '{value}'", f"found '{value}' in response"))
                    return False
            return True
        return True

    def _check_assertion(self, field: str, expected: Any, actual: Any) -> bool:
        if isinstance(expected, str) and expected.startswith("@"):
            return self._eval_smart_assertion(field, expected, actual)
        if expected != actual:
            self.results.append(AssertionError_(field, repr(expected), actual))
            return False
        return True

    def _eval_smart_assertion(self, field: str, expr: str, actual: Any) -> bool:
        expr = expr.strip()

        # @notNull
        if expr == "@notNull":
            if actual is None:
                self.results.append(AssertionError_(field, "not null", actual))
                return False
            return True

        # @isNull
        if expr == "@isNull":
            if actual is not None:
                self.results.append(AssertionError_(field, "null", actual))
                return False
            return True

        # @gt(N)
        m = re.match(r'@gt\((.+)\)', expr)
        if m:
            threshold = float(m.group(1))
            if not isinstance(actual, (int, float)) or actual <= threshold:
                self.results.append(AssertionError_(field, f"> {threshold}", actual))
                return False
            return True

        # @gte(N)
        m = re.match(r'@gte\((.+)\)', expr)
        if m:
            threshold = float(m.group(1))
            if not isinstance(actual, (int, float)) or actual < threshold:
                self.results.append(AssertionError_(field, f">= {threshold}", actual))
                return False
            return True

        # @lt(N)
        m = re.match(r'@lt\((.+)\)', expr)
        if m:
            threshold = float(m.group(1))
            if not isinstance(actual, (int, float)) or actual >= threshold:
                self.results.append(AssertionError_(field, f"< {threshold}", actual))
                return False
            return True

        # @lte(N)
        m = re.match(r'@lte\((.+)\)', expr)
        if m:
            threshold = float(m.group(1))
            if not isinstance(actual, (int, float)) or actual > threshold:
                self.results.append(AssertionError_(field, f"<= {threshold}", actual))
                return False
            return True

        # @in([...])
        m = re.match(r'@in\((\[.+\])\)', expr)
        if m:
            allowed = json.loads(m.group(1))
            if actual not in allowed:
                self.results.append(AssertionError_(field, f"in {allowed}", actual))
                return False
            return True

        # @notEqual(V)
        m = re.match(r"@notEqual\(['\"]?(.+?)['\"]?\)", expr)
        if m:
            forbidden = m.group(1)
            if str(actual) == forbidden:
                self.results.append(AssertionError_(field, f"!= '{forbidden}'", actual))
                return False
            return True

        # @contains(S)
        m = re.match(r"@contains\(['\"](.+?)['\"]\)", expr)
        if m:
            substring = m.group(1)
            if not isinstance(actual, str) or substring not in actual:
                self.results.append(AssertionError_(field, f"contains '{substring}'", actual))
                return False
            return True

        # @not_contains(S)
        m = re.match(r"@not_contains\(['\"](.+?)['\"]\)", expr)
        if m:
            substring = m.group(1)
            actual_str = str(actual) if actual else ""
            if substring.lower() in actual_str.lower():
                self.results.append(AssertionError_(field, f"not contains '{substring}'", actual))
                return False
            return True

        # @matches(regex)
        m = re.match(r"@matches\((.+)\)", expr)
        if m:
            pattern = m.group(1)
            if not isinstance(actual, str) or not re.search(pattern, actual):
                self.results.append(AssertionError_(field, f"matches /{pattern}/", actual))
                return False
            return True

        # @startsWith(S)
        m = re.match(r"@startsWith\(['\"](.+?)['\"]\)", expr)
        if m:
            prefix = m.group(1)
            if not isinstance(actual, str) or not actual.startswith(prefix):
                self.results.append(AssertionError_(field, f"starts with '{prefix}'", actual))
                return False
            return True

        # @endsWith(S)
        m = re.match(r"@endsWith\(['\"](.+?)['\"]\)", expr)
        if m:
            suffix = m.group(1)
            if not isinstance(actual, str) or not actual.endswith(suffix):
                self.results.append(AssertionError_(field, f"ends with '{suffix}'", actual))
                return False
            return True

        # @size(N)
        m = re.match(r'@size\((\d+)\)', expr)
        if m:
            expected_size = int(m.group(1))
            actual_size = len(actual) if actual else 0
            if actual_size != expected_size:
                self.results.append(AssertionError_(field, f"size == {expected_size}", f"size == {actual_size}"))
                return False
            return True

        # @minSize(N)
        m = re.match(r'@minSize\((\d+)\)', expr)
        if m:
            min_size = int(m.group(1))
            actual_size = len(actual) if actual else 0
            if actual_size < min_size:
                self.results.append(AssertionError_(field, f"size >= {min_size}", f"size == {actual_size}"))
                return False
            return True

        # @maxSize(N)
        m = re.match(r'@maxSize\((\d+)\)', expr)
        if m:
            max_size = int(m.group(1))
            actual_size = len(actual) if actual else 0
            if actual_size > max_size:
                self.results.append(AssertionError_(field, f"size <= {max_size}", f"size == {actual_size}"))
                return False
            return True

        # @isString / @isNumber / @isArray
        if expr == "@isString":
            if not isinstance(actual, str):
                self.results.append(AssertionError_(field, "is string", type(actual).__name__))
                return False
            return True
        if expr == "@isNumber":
            if not isinstance(actual, (int, float)):
                self.results.append(AssertionError_(field, "is number", type(actual).__name__))
                return False
            return True
        if expr == "@isArray":
            if not isinstance(actual, list):
                self.results.append(AssertionError_(field, "is array", type(actual).__name__))
                return False
            return True

        # 未知断言
        self.results.append(AssertionError_(field, f"unknown assertion: {expr}", actual))
        return False

    def _get_nested(self, obj: Any, path: str) -> Any:
        parts = path.split(".")
        current = obj
        for part in parts:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current
