"""
代码反查器：从接口 URL 定位到源码文件，并追踪调用链
"""

import os
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from .detector import ProjectInfo
from .route_extractor import RouteExtractor


@dataclass
class CodeFile:
    path: str
    content: str
    role: str       # controller, service, validator, mapper, model, middleware
    line_match: int = 0


@dataclass
class CodeContext:
    url: str
    method: str
    files: list = field(default_factory=list)
    entry_file: str = ""
    call_chain: list = field(default_factory=list)


class CodeLocator:
    def __init__(self, project_path: str, project_info: ProjectInfo):
        self.project_path = Path(project_path).resolve()
        self.project_info = project_info
        self.max_depth = 3
        self.max_files = 10

    def locate(self, url: str, method: str = None) -> CodeContext:
        ctx = CodeContext(url=url, method=method or "")

        # Step 1: prefer framework-aware route extraction.
        route_matches = RouteExtractor(str(self.project_path), self.project_info).find_matches(url, method)
        if route_matches:
            for route in route_matches[:3]:
                fpath = Path(route.file)
                content = self._read_file(fpath)
                if content:
                    role = self._infer_role(fpath, content)
                    ctx.files.append(CodeFile(
                        path=str(fpath),
                        content=content,
                        role=role,
                        line_match=route.line,
                    ))
                    if not ctx.entry_file:
                        ctx.entry_file = str(fpath)
                    ctx.call_chain.append(f"{route.method} {route.path} → {route.handler or fpath.name}")

            if ctx.files:
                self._trace_calls(ctx, depth=0)
                return ctx

        # Step 2: fallback to grep for unsupported frameworks or unusual routes.
        entry_files = self._grep_url(url)
        if not entry_files:
            url_parts = url.rstrip("/").split("/")
            if len(url_parts) > 2:
                partial = "/".join(url_parts[-2:])
                entry_files = self._grep_url(partial)

        if not entry_files:
            return ctx

        # Step 3: read matched files.
        for fpath, line_num in entry_files[:3]:
            content = self._read_file(fpath)
            if content:
                role = self._infer_role(fpath, content)
                ctx.files.append(CodeFile(
                    path=str(fpath),
                    content=content,
                    role=role,
                    line_match=line_num,
                ))
                if not ctx.entry_file:
                    ctx.entry_file = str(fpath)

        # Step 4: trace call chain.
        if ctx.files:
            self._trace_calls(ctx, depth=0)

        return ctx

    def _grep_url(self, url: str) -> list:
        results = []
        url_escaped = re.escape(url)
        url_pattern = url_escaped.replace(r"\{", "[^}]*").replace(r"\}", "[^}]*")

        for entry_dir in self.project_info.entry_dirs:
            if not os.path.isdir(entry_dir):
                continue
            try:
                extensions = self.project_info.file_ext.split(",")
                include_args = []
                for ext in extensions:
                    include_args.extend(["--include", ext.strip()])

                cmd = [
                    "grep", "-rn", "--color=never",
                    *include_args,
                    url,
                    entry_dir,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, timeout=10
                )
                stdout = result.stdout.decode("utf-8", errors="ignore")
                for line in stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split(":", 2)
                    if len(parts) >= 2:
                        fpath = parts[0]
                        try:
                            line_num = int(parts[1])
                        except ValueError:
                            line_num = 0
                        results.append((Path(fpath), line_num))
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue

        return results

    def _read_file(self, fpath: Path) -> str:
        try:
            return fpath.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def _infer_role(self, fpath: Path, content: str) -> str:
        name = fpath.name.lower()
        lang = self.project_info.language

        if lang == "java":
            if "controller" in name or "@RestController" in content or "@Controller" in content:
                return "controller"
            if "service" in name and ("@Service" in content or "interface" not in content):
                return "service"
            if "validator" in name or "Validator" in content:
                return "validator"
            if "mapper" in name or "Mapper" in content or "@Mapper" in content:
                return "mapper"
            if "dto" in name or "request" in name or "response" in name or "vo" in name:
                return "model"
        elif lang in ("python",):
            if "@router." in content or "@app." in content or "FastAPI(" in content or "APIRouter(" in content:
                return "controller"
            if "view" in name or "router" in name or "controller" in name or "endpoint" in name:
                return "controller"
            if "service" in name:
                return "service"
            if "schema" in name or "model" in name or "serializer" in name:
                return "model"
        elif lang == "go":
            if "handler" in name or "controller" in name:
                return "controller"
            if "service" in name:
                return "service"
            if "model" in name or "entity" in name:
                return "model"
            if "middleware" in name:
                return "middleware"

        return "unknown"

    def _trace_calls(self, ctx: CodeContext, depth: int):
        if depth >= self.max_depth or len(ctx.files) >= self.max_files:
            return

        entry_content = ctx.files[0].content
        lang = self.project_info.language
        referenced_files = []

        if lang == "java":
            referenced_files = self._trace_java_calls(entry_content, ctx)
        elif lang == "python":
            referenced_files = self._trace_python_calls(entry_content, ctx)
        elif lang == "go":
            referenced_files = self._trace_go_calls(entry_content, ctx)

        for fpath in referenced_files:
            if len(ctx.files) >= self.max_files:
                break
            if any(f.path == str(fpath) for f in ctx.files):
                continue
            content = self._read_file(fpath)
            if content:
                role = self._infer_role(fpath, content)
                ctx.files.append(CodeFile(path=str(fpath), content=content, role=role))
                ctx.call_chain.append(f"{ctx.files[-2].path} → {str(fpath)}")

    def _trace_java_calls(self, content: str, ctx: CodeContext) -> list:
        results = []
        # 找 @Autowired / @Resource 注入的类
        injections = re.findall(
            r'(?:@Autowired|@Resource|@Inject)\s+(?:private\s+)?(\w+)\s+\w+',
            content
        )
        # 也找构造器注入
        constructor_params = re.findall(
            r'(?:private\s+final\s+)(\w+)\s+\w+',
            content
        )
        class_names = set(injections + constructor_params)

        # 找这些类对应的文件
        for class_name in class_names:
            if class_name in ("String", "List", "Map", "Set", "Integer", "Long", "Boolean"):
                continue
            found = self._find_java_class(class_name)
            if found:
                results.append(found)

        # 找 DTO/Request/Response 类 (支持 @RequestBody 和 @X5RequestBody，含泛型，跨行)
        lines = content.splitlines()
        body_re = re.compile(r'@(?:RequestBody|X5RequestBody)\b')
        type_re = re.compile(r'(?:^|[\s(,])([A-Z]\w+)(?:<([A-Z]\w+)>)?\s+\w+')
        skip_names = {"Valid", "NotNull", "NotEmpty", "NotBlank", "RequestBody", "X5RequestBody",
                      "String", "List", "Map", "Set", "Integer", "Long", "Boolean", "Object"}
        for i, line in enumerate(lines):
            body_match = body_re.search(line)
            if not body_match:
                continue
            # Search from after the @Body annotation
            after_body = line[body_match.end():]
            block = after_body
            for j in range(1, 4):
                if i + j < len(lines):
                    block += " " + lines[i + j].strip()
                m = type_re.search(block)
                if m and m.group(1) not in skip_names:
                    if m.group(2):
                        found = self._find_java_class(m.group(2))
                        if found:
                            results.append(found)
                    found = self._find_java_class(m.group(1))
                    if found:
                        results.append(found)
                    break

        return results[:5]

    def _find_java_class(self, class_name: str) -> Path:
        target = f"{class_name}.java"
        for entry_dir in self.project_info.entry_dirs:
            entry_path = Path(entry_dir)
            if not entry_path.is_dir():
                continue
            for found in entry_path.rglob(target):
                if found.is_file():
                    return found
        return None

    def _trace_python_calls(self, content: str, ctx: CodeContext) -> list:
        results = []
        imports = re.findall(r'from\s+(\S+)\s+import', content)
        for imp in imports:
            module_path = imp.replace(".", "/")
            for entry_dir in self.project_info.entry_dirs:
                candidate = Path(entry_dir) / f"{module_path}.py"
                if candidate.exists():
                    results.append(candidate)
                    break
        return results[:5]

    def _trace_go_calls(self, content: str, ctx: CodeContext) -> list:
        results = []
        # 找函数调用中的 service/repo 引用
        calls = re.findall(r'(\w+)\.(\w+)\(', content)
        for receiver, _ in calls:
            if receiver[0].isupper():
                found = self._find_go_file(receiver)
                if found:
                    results.append(found)
        return results[:5]

    def _find_go_file(self, type_name: str) -> Path:
        try:
            cmd = [
                "grep", "-rl", f"type {type_name} struct",
                str(self.project_path),
                "--include=*.go",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            for line in result.stdout.strip().split("\n"):
                if line:
                    return Path(line)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None
