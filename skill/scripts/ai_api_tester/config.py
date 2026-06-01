"""Load project-level .ai-api-tester.yaml configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


CONFIG_FILENAME = ".ai-api-tester.yaml"


@dataclass
class ProjectConfig:
    """Project-specific configuration for ai-api-tester."""

    # Custom mapping annotations treated like @RequestMapping (default to POST)
    custom_mapping_annotations: list[str] = field(default_factory=list)
    # Custom body annotations treated like @RequestBody
    custom_body_annotations: list[str] = field(default_factory=list)
    # Custom doc annotations to extract description (format: "AnnotationName.fieldName")
    doc_annotations: list[str] = field(default_factory=list)
    # Extra entry directories beyond auto-detected ones
    extra_entry_dirs: list[str] = field(default_factory=list)
    # Modules to skip during scanning
    skip_modules: list[str] = field(default_factory=list)


def load_config(project_path: str) -> ProjectConfig:
    """Load .ai-api-tester.yaml from the project root. Returns defaults if missing."""
    config_file = Path(project_path).resolve() / CONFIG_FILENAME
    if not config_file.exists():
        return ProjectConfig()

    if yaml is None:
        # Fallback: simple key-value parsing for basic lists
        return _parse_simple(config_file)

    try:
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ProjectConfig()
        return _from_dict(data)
    except Exception:
        return ProjectConfig()


def _from_dict(data: dict[str, Any]) -> ProjectConfig:
    return ProjectConfig(
        custom_mapping_annotations=_as_list(data.get("custom_mapping_annotations")),
        custom_body_annotations=_as_list(data.get("custom_body_annotations")),
        doc_annotations=_as_list(data.get("doc_annotations")),
        extra_entry_dirs=_as_list(data.get("extra_entry_dirs")),
        skip_modules=_as_list(data.get("skip_modules")),
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _parse_simple(config_file: Path) -> ProjectConfig:
    """Minimal YAML-subset parser for when PyYAML is not installed."""
    data: dict[str, list[str]] = {}
    current_key = ""
    try:
        for line in config_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith(":") and not stripped.startswith("-"):
                current_key = stripped[:-1].strip()
                data[current_key] = []
            elif stripped.startswith("- ") and current_key:
                data[current_key].append(stripped[2:].strip().strip("\"'"))
    except OSError:
        pass
    return _from_dict(data)
