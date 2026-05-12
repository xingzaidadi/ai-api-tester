"""
信息源增强：Git 历史分析 + Schema 分析
"""

import subprocess
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


@dataclass
class GitRiskInfo:
    risk_score: float                    # 0-10
    recent_changes: int                  # 近30天变更次数
    recent_fix_commits: List[str] = field(default_factory=list)
    hot_files: List[str] = field(default_factory=list)
    last_modified: str = ""
    risk_factors: List[str] = field(default_factory=list)


@dataclass
class SchemaConstraint:
    table: str
    column: str
    constraint_type: str   # not_null, unique, foreign_key, check, enum, decimal_precision
    detail: str


class GitAnalyzer:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()

    def analyze_risk(self, file_paths: List[str]) -> GitRiskInfo:
        info = GitRiskInfo(risk_score=0.0, recent_changes=0)

        if not file_paths:
            return info

        for fpath in file_paths:
            rel_path = self._relative_path(fpath)
            if not rel_path:
                continue

            # 近30天修改次数
            changes = self._count_recent_changes(rel_path, days=30)
            info.recent_changes += changes

            # 近期 fix 提交
            fixes = self._find_fix_commits(rel_path)
            info.recent_fix_commits.extend(fixes)

            # 最近修改时间
            last_mod = self._last_modified(rel_path)
            if last_mod:
                info.last_modified = last_mod

        # 热点文件（项目级）
        info.hot_files = self._find_hot_files(days=30, top=5)

        # 计算风险评分
        info.risk_score = self._calculate_risk_score(info)
        info.risk_factors = self._build_risk_factors(info)

        return info

    def _relative_path(self, fpath: str) -> str:
        try:
            return str(Path(fpath).relative_to(self.project_path))
        except ValueError:
            return fpath

    def _count_recent_changes(self, rel_path: str, days: int) -> int:
        try:
            cmd = [
                "git", "-C", str(self.project_path),
                "log", f"--since={days} days ago",
                "--oneline", "--", rel_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            lines = [l for l in result.stdout.strip().split("\n") if l]
            return len(lines)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return 0

    def _find_fix_commits(self, rel_path: str) -> List[str]:
        try:
            cmd = [
                "git", "-C", str(self.project_path),
                "log", "--since=90 days ago",
                "--oneline", "--grep=fix", "-i",
                "--", rel_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            return lines[:5]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _last_modified(self, rel_path: str) -> str:
        try:
            cmd = [
                "git", "-C", str(self.project_path),
                "log", "-1", "--format=%ci", "--", rel_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _find_hot_files(self, days: int, top: int) -> List[str]:
        try:
            cmd = [
                "git", "-C", str(self.project_path),
                "log", f"--since={days} days ago",
                "--name-only", "--pretty=format:"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            files = [l.strip() for l in result.stdout.split("\n") if l.strip()]

            # 统计频率
            freq = {}
            for f in files:
                freq[f] = freq.get(f, 0) + 1
            sorted_files = sorted(freq.items(), key=lambda x: -x[1])
            return [f"{f} ({count}次)" for f, count in sorted_files[:top]]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def _calculate_risk_score(self, info: GitRiskInfo) -> float:
        score = 0.0

        # 近期修改频率（0-4分）
        if info.recent_changes >= 10:
            score += 4.0
        elif info.recent_changes >= 5:
            score += 3.0
        elif info.recent_changes >= 3:
            score += 2.0
        elif info.recent_changes >= 1:
            score += 1.0

        # 历史 fix 提交（0-3分）
        fix_count = len(info.recent_fix_commits)
        if fix_count >= 5:
            score += 3.0
        elif fix_count >= 3:
            score += 2.0
        elif fix_count >= 1:
            score += 1.0

        # 是否在热点文件中（0-3分）
        if info.hot_files:
            score += min(3.0, len(info.hot_files) * 0.6)

        return min(10.0, score)

    def _build_risk_factors(self, info: GitRiskInfo) -> List[str]:
        factors = []
        if info.recent_changes >= 5:
            factors.append(f"近30天修改{info.recent_changes}次，变更频繁")
        if info.recent_fix_commits:
            factors.append(f"近3个月有{len(info.recent_fix_commits)}个fix提交")
        if info.last_modified:
            factors.append(f"最后修改: {info.last_modified[:10]}")
        return factors


class SchemaAnalyzer:
    def __init__(self, project_path: str, language: str = "java"):
        self.project_path = Path(project_path).resolve()
        self.language = language

    def analyze_entity(self, file_paths: List[str]) -> List[SchemaConstraint]:
        constraints = []

        for fpath in file_paths:
            content = self._read_file(fpath)
            if not content:
                continue

            if self.language == "java":
                constraints.extend(self._parse_java_entity(content, fpath))
            elif self.language == "python":
                constraints.extend(self._parse_python_model(content, fpath))
            elif self.language == "go":
                constraints.extend(self._parse_go_struct(content, fpath))

        return constraints

    def _read_file(self, fpath: str) -> str:
        try:
            return Path(fpath).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _parse_java_entity(self, content: str, fpath: str) -> List[SchemaConstraint]:
        constraints = []
        table_name = ""

        # 提取表名
        m = re.search(r'@Table\s*\(\s*name\s*=\s*"(\w+)"', content)
        if m:
            table_name = m.group(1)

        # 提取类名作为备用表名
        m = re.search(r'class\s+(\w+)', content)
        class_name = m.group(1) if m else "unknown"
        if not table_name:
            table_name = class_name

        # 找字段和注解
        # @Column(nullable = false)
        for m in re.finditer(r'@Column\s*\([^)]*nullable\s*=\s*false[^)]*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(1), "not_null", "数据库非空约束"))

        # @Column(unique = true)
        for m in re.finditer(r'@Column\s*\([^)]*unique\s*=\s*true[^)]*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(1), "unique", "唯一约束，重复值应返回409"))

        # @Column(precision, scale) — DECIMAL
        for m in re.finditer(r'@Column\s*\([^)]*precision\s*=\s*(\d+)[^)]*scale\s*=\s*(\d+)[^)]*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(3), "decimal_precision", f"DECIMAL({m.group(1)},{m.group(2)})"))

        # @Column(length = N)
        for m in re.finditer(r'@Column\s*\([^)]*length\s*=\s*(\d+)[^)]*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(2), "max_length", f"最大长度{m.group(1)}"))

        # @Enumerated
        for m in re.finditer(r'@Enumerated\s*\([^)]*\)\s*(?:private\s+)?(\w+)\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(2), "enum", f"枚举类型 {m.group(1)}"))

        # JSR-303 注解
        for m in re.finditer(r'@NotNull\s+(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(1), "not_null", "NotNull校验"))

        for m in re.finditer(r'@NotBlank\s+(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(1), "not_blank", "不能为空字符串"))

        for m in re.finditer(r'@Size\s*\(\s*(?:min\s*=\s*(\d+))?\s*,?\s*(?:max\s*=\s*(\d+))?\s*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            detail = f"Size(min={m.group(1) or '?'}, max={m.group(2) or '?'})"
            constraints.append(SchemaConstraint(table_name, m.group(3), "size", detail))

        for m in re.finditer(r'@Min\s*\(\s*(\d+)\s*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(2), "min_value", f"最小值{m.group(1)}"))

        for m in re.finditer(r'@Max\s*\(\s*(\d+)\s*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(2), "max_value", f"最大值{m.group(1)}"))

        for m in re.finditer(r'@Pattern\s*\(\s*regexp\s*=\s*"([^"]+)"\s*\)\s*(?:private\s+)?\w+\s+(\w+)', content):
            constraints.append(SchemaConstraint(table_name, m.group(2), "pattern", f"正则: {m.group(1)}"))

        return constraints

    def _parse_python_model(self, content: str, fpath: str) -> List[SchemaConstraint]:
        constraints = []
        class_name = ""

        m = re.search(r'class\s+(\w+)', content)
        if m:
            class_name = m.group(1)

        # Pydantic Field
        for m in re.finditer(r'(\w+)\s*:\s*\w+\s*=\s*Field\(([^)]+)\)', content):
            field_name = m.group(1)
            field_args = m.group(2)

            if "min_length" in field_args:
                constraints.append(SchemaConstraint(class_name, field_name, "min_length", field_args.strip()))
            if "max_length" in field_args:
                constraints.append(SchemaConstraint(class_name, field_name, "max_length", field_args.strip()))
            if "ge=" in field_args or "gt=" in field_args:
                constraints.append(SchemaConstraint(class_name, field_name, "min_value", field_args.strip()))
            if "le=" in field_args or "lt=" in field_args:
                constraints.append(SchemaConstraint(class_name, field_name, "max_value", field_args.strip()))

        # SQLAlchemy Column
        for m in re.finditer(r'(\w+)\s*=\s*Column\(([^)]+)\)', content):
            col_name = m.group(1)
            col_args = m.group(2)

            if "nullable=False" in col_args:
                constraints.append(SchemaConstraint(class_name, col_name, "not_null", "nullable=False"))
            if "unique=True" in col_args:
                constraints.append(SchemaConstraint(class_name, col_name, "unique", "unique=True"))

        return constraints

    def _parse_go_struct(self, content: str, fpath: str) -> List[SchemaConstraint]:
        constraints = []
        struct_name = ""

        m = re.search(r'type\s+(\w+)\s+struct', content)
        if m:
            struct_name = m.group(1)

        # 解析 struct tag: `binding:"required,min=1,max=100"`
        for m in re.finditer(r'(\w+)\s+\w+\s+`[^`]*binding:"([^"]+)"[^`]*`', content):
            field_name = m.group(1)
            binding = m.group(2)

            if "required" in binding:
                constraints.append(SchemaConstraint(struct_name, field_name, "not_null", "binding:required"))
            min_m = re.search(r'min=(\d+)', binding)
            if min_m:
                constraints.append(SchemaConstraint(struct_name, field_name, "min_value", f"min={min_m.group(1)}"))
            max_m = re.search(r'max=(\d+)', binding)
            if max_m:
                constraints.append(SchemaConstraint(struct_name, field_name, "max_value", f"max={max_m.group(1)}"))

        # GORM tag: `gorm:"uniqueIndex"` / `gorm:"not null"`
        for m in re.finditer(r'(\w+)\s+\w+\s+`[^`]*gorm:"([^"]+)"[^`]*`', content):
            field_name = m.group(1)
            gorm_tag = m.group(2)

            if "uniqueIndex" in gorm_tag or "unique" in gorm_tag:
                constraints.append(SchemaConstraint(struct_name, field_name, "unique", "gorm:unique"))
            if "not null" in gorm_tag:
                constraints.append(SchemaConstraint(struct_name, field_name, "not_null", "gorm:not null"))

        return constraints
