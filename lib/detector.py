"""
项目探测器：自动识别项目的语言和框架
"""

import os
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ProjectInfo:
    language: str          # java, python, go, typescript, javascript
    framework: str         # spring-boot, fastapi, django, gin, echo, express, nestjs
    entry_dirs: list       # 源码入口目录
    file_ext: str          # 源码文件扩展名
    route_patterns: list   # 路由匹配正则


FRAMEWORK_DETECTORS = [
    {
        "name": "spring-boot",
        "language": "java",
        "signals": [
            ("pom.xml", "spring-boot"),
            ("build.gradle", "spring-boot"),
            ("build.gradle.kts", "spring-boot"),
        ],
        "entry_dirs": ["src/main/java"],
        "file_ext": "*.java",
        "route_patterns": [
            r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(',
            r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\s*\(',
        ],
    },
    {
        "name": "fastapi",
        "language": "python",
        "signals": [
            ("requirements.txt", "fastapi"),
            ("pyproject.toml", "fastapi"),
            ("Pipfile", "fastapi"),
        ],
        "entry_dirs": ["app", "src", "."],
        "file_ext": "*.py",
        "route_patterns": [
            r'@(app|router)\.(get|post|put|delete|patch)\s*\(',
        ],
    },
    {
        "name": "django-rest",
        "language": "python",
        "signals": [
            ("requirements.txt", "djangorestframework"),
            ("pyproject.toml", "djangorestframework"),
            ("manage.py", None),
        ],
        "entry_dirs": ["."],
        "file_ext": "*.py",
        "route_patterns": [
            r'path\s*\(',
            r'url\s*\(',
            r'@action\s*\(',
        ],
    },
    {
        "name": "flask",
        "language": "python",
        "signals": [
            ("requirements.txt", "flask"),
            ("pyproject.toml", "flask"),
        ],
        "entry_dirs": ["app", "src", "."],
        "file_ext": "*.py",
        "route_patterns": [
            r'@(app|blueprint|bp)\.(route|get|post|put|delete)\s*\(',
        ],
    },
    {
        "name": "gin",
        "language": "go",
        "signals": [
            ("go.mod", "gin-gonic"),
        ],
        "entry_dirs": ["internal", "cmd", "api", "handler", "router", "."],
        "file_ext": "*.go",
        "route_patterns": [
            r'\.(GET|POST|PUT|DELETE|PATCH|Handle)\s*\(',
        ],
    },
    {
        "name": "echo",
        "language": "go",
        "signals": [
            ("go.mod", "labstack/echo"),
        ],
        "entry_dirs": ["internal", "cmd", "api", "handler", "."],
        "file_ext": "*.go",
        "route_patterns": [
            r'\.(GET|POST|PUT|DELETE|PATCH)\s*\(',
        ],
    },
    {
        "name": "express",
        "language": "javascript",
        "signals": [
            ("package.json", "express"),
        ],
        "entry_dirs": ["src", "routes", "controllers", "."],
        "file_ext": "*.js",
        "route_patterns": [
            r'(router|app)\.(get|post|put|delete|patch)\s*\(',
        ],
    },
    {
        "name": "nestjs",
        "language": "typescript",
        "signals": [
            ("package.json", "@nestjs/core"),
        ],
        "entry_dirs": ["src"],
        "file_ext": "*.ts",
        "route_patterns": [
            r'@(Get|Post|Put|Delete|Patch)\s*\(',
        ],
    },
]


class ProjectDetector:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()

    def detect(self) -> ProjectInfo:
        for detector in FRAMEWORK_DETECTORS:
            if self._match_signals(detector["signals"]):
                entry_dirs = self._resolve_entry_dirs(detector["entry_dirs"])
                return ProjectInfo(
                    language=detector["language"],
                    framework=detector["name"],
                    entry_dirs=entry_dirs,
                    file_ext=detector["file_ext"],
                    route_patterns=detector["route_patterns"],
                )
        return self._fallback_detect()

    def _match_signals(self, signals: list) -> bool:
        for filename, keyword in signals:
            filepath = self.project_path / filename
            if filepath.exists():
                if keyword is None:
                    return True
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    if keyword in content:
                        return True
                except (OSError, UnicodeDecodeError):
                    continue
        return False

    def _resolve_entry_dirs(self, dirs: list) -> list:
        resolved = []
        for d in dirs:
            full_path = self.project_path / d
            if full_path.exists() and full_path.is_dir():
                resolved.append(str(full_path))
        return resolved if resolved else [str(self.project_path)]

    def _fallback_detect(self) -> ProjectInfo:
        if (self.project_path / "go.mod").exists():
            return ProjectInfo("go", "unknown-go", [str(self.project_path)], "*.go", [])
        if (self.project_path / "pom.xml").exists() or (self.project_path / "build.gradle").exists():
            return ProjectInfo("java", "unknown-java", [str(self.project_path / "src/main/java")], "*.java", [])
        if (self.project_path / "requirements.txt").exists() or (self.project_path / "pyproject.toml").exists():
            return ProjectInfo("python", "unknown-python", [str(self.project_path)], "*.py", [])
        if (self.project_path / "package.json").exists():
            return ProjectInfo("javascript", "unknown-js", [str(self.project_path / "src")], "*.ts,*.js", [])
        return ProjectInfo("unknown", "unknown", [str(self.project_path)], "*.*", [])
