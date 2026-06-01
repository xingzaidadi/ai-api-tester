# AI API Tester 踩坑指南

基于 priceCenterServer 等真实项目的实践总结。

---

## 1. 多模块 Maven 项目检测不到

**现象**: `detect.py` 输出 `unknown` 或只识别到根目录。

**原因**: pom.xml 不在项目根目录，而在子模块中（如 `isc-server-price/server/pom.xml`）。

**解决方案**: 探测器已改为递归搜索（3层深度），自动发现子模块。如果仍检测不到，检查：
- 确认 pom.xml/build.gradle 中包含 `spring-boot` 关键字
- 如果目录层级 > 3，可在 `.ai-api-tester.yaml` 中配置 `extra_entry_dirs`

```yaml
# .ai-api-tester.yaml
extra_entry_dirs:
  - "deep/nested/module/src/main/java"
```

---

## 2. 自定义注解路由无法识别

**现象**: `locate.py` 找不到接口，`auto.py --validate-only` 显示 0 routes。

**原因**: 项目使用自定义路由注解（如小米的 `@X5RequestMapping`），不在标准 Spring 注解列表中。

**解决方案**: 

方案 A（零配置）：代码已内置 `@X5RequestMapping` 支持。

方案 B（其他自定义注解）：在项目根目录创建 `.ai-api-tester.yaml`：

```yaml
custom_mapping_annotations:
  - "MyCustomMapping"
  - "InternalPostMapping"

custom_body_annotations:
  - "MyRequestBody"
  - "X5RequestBody"
```

---

## 3. 泛型包装类导致 fields=0

**现象**: `test_basis.fields` 为空，即使接口有明确的 Request DTO。

**原因**: 接口签名是 `@RequestBody ParamWrapper<PullPriceX5Req> req`，旧版只捕获到 `ParamWrapper` 而非真正的业务类 `PullPriceX5Req`。

**解决方案**: 已修复。现在支持多种模式：
- `@RequestBody ParamWrapper<PullPriceX5Req> req` → 追踪 ParamWrapper 和 PullPriceX5Req
- `@RequestBody List<SomeReq> reqList` → 过滤 List，追踪 SomeReq
- `@X5RequestBody @Valid @NotNull(...)\n  ParamWrapper<Req> param` → 跨行匹配

还支持自动从跨模块目录查找 DTO 类文件（如 DTO 在 sdk 模块，Controller 在 client 模块）。

如果你的包装类更复杂（如 `Wrapper<A, B>`），当前只取第一个泛型参数。

---

## 4. UnicodeEncodeError 写文件失败

**现象**: `gen_context.py` 报 `UnicodeEncodeError: 'utf-8' codec can't encode...` 或 `'gbk' codec can't encode...`。

**原因**: 
- Java 源文件使用 GBK 编码（中文注释），读取时部分字符无法编码
- Windows 终端默认 GBK，print 含 emoji 的字符串失败

**解决方案**:
- 文件读取：已使用 `errors="ignore"` 容错
- 文件写入：已使用 `errors="replace"` 替换无法编码的字符
- 控制台输出：在需要的脚本中用 `io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")` 包装

---

## 5. Git Bash 路径篡改

**现象**: 在 Git Bash 中运行时，`/api/v1/orders` 被自动转换为 `D:/tools/Git/api/v1/orders`。

**原因**: Git Bash (MSYS2) 会对以 `/` 开头的参数自动进行路径转换。

**解决方案**:
- 方案 A：使用 CMD 或 PowerShell 运行脚本
- 方案 B：设置环境变量 `MSYS_NO_PATHCONV=1`
- 方案 C：用双斜杠前缀 `//api/v1/orders`（MSYS2 不会转换双斜杠）

```bash
# Git Bash 中
MSYS_NO_PATHCONV=1 python3 scripts/locate.py /api/v1/orders ./project

# 或者直接用 CMD/PowerShell
python scripts/locate.py /api/v1/orders ./project
```

---

## 6. 跨模块类找不到

**现象**: Controller 在 server 模块，但 DTO 在 client 模块，`locator.py` 没有追踪到 DTO 文件。

**原因**: `_find_java_class` 在所有 entry_dirs 中搜索，但 entry_dirs 可能没有包含 client 模块。

**解决方案**: 探测器已改进为递归发现所有子模块的 `src/main/java` 目录。确认：
```bash
python3 scripts/detect.py /path/to/project
```
输出的 `entry_dirs` 应包含所有子模块路径。如果缺少，在 `.ai-api-tester.yaml` 中补充。

---

## 7. route_extractor 只找到部分路由

**现象**: 项目有 20 个接口，但只发现 5 个。

**可能原因**:
1. 部分接口用了非标准注解（见问题 2）
2. 部分接口定义在内部类中
3. 路由注解跨多行但括号不平衡

**排查方法**:
```bash
# 列出所有识别到的路由
python3 scripts/auto.py /path/to/project --validate-only
```

比对实际接口数量。如果缺失，检查对应 Controller 的注解格式。

---

## 8. @HttpApiDoc 注解信息未提取

**现象**: 路由的 `description` 字段为空，尽管源码中有 `@HttpApiDoc(apiName="xxx")`。

**原因**: `@HttpApiDoc` 注解必须在 `@XxxMapping` 注解的上方 8 行以内才会被提取。

**解决方案**: 确保 `@HttpApiDoc` 直接标注在方法上，且紧邻 `@Mapping` 注解：
```java
@HttpApiDoc(apiName = "拉取价格模型接口")  // 在 Mapping 上方
@X5RequestMapping("/pullPrice")
public Result pullPrice(@X5RequestBody ParamWrapper<PullPriceReq> req) { ... }
```

---

## 9. validate_cases.py 拒绝 YAML

**常见原因**:
- `concurrency` 字段：当前不支持，不要生成
- `setup`/`teardown` 中使用了未支持的 action 类型
- `expect.body` 中使用了不存在的 matcher（参考 `references/assertions.md`）
- `request.headers` 不是 dict 类型

**快速修复**: 阅读 validate 输出的具体错误信息，对照 `references/yaml_format.md` 修正。

---

## 10. Windows 下 find 命令不可用

**现象**: `locator.py` 的 `_find_java_class` 调用 `find` 命令失败。

**原因**: Windows 的 `find` 是文本搜索命令，不是 Unix 的 `find`。脚本依赖 Unix 工具链。

**解决方案**: 
- 确保 PATH 中有 Git for Windows 的 `/usr/bin`（Git Bash 自带 Unix 工具）
- 或者在 WSL 环境中运行
- 或者安装 MSYS2/Cygwin

如果在纯 Windows CMD 中运行，建议通过 Claude Code 的 bash shell 执行（它自动使用 Git Bash）。

---

## 配置文件模板

在项目根目录创建 `.ai-api-tester.yaml`：

```yaml
# AI API Tester 项目配置
# 放在项目根目录

# 自定义路由注解（默认行为等同 POST @RequestMapping）
custom_mapping_annotations:
  - "X5RequestMapping"

# 自定义请求体注解（等同 @RequestBody）
custom_body_annotations:
  - "X5RequestBody"

# 文档注解（用于提取接口名称）
doc_annotations:
  - "HttpApiDoc.apiName"

# 额外源码目录（补充自动探测结果）
extra_entry_dirs: []

# 跳过的模块目录
skip_modules:
  - "test"
  - "benchmark"
```

---

## 快速验证清单

在新项目上使用前，依次检查：

1. `python3 scripts/detect.py <project>` → 确认 language/framework 正确
2. `python3 scripts/auto.py <project> --validate-only` → 确认路由数量合理
3. `python3 scripts/locate.py <一个已知URL> <project>` → 确认能找到源文件
4. `python3 scripts/gen_context.py <URL> <project> --output test.json` → 确认 test_basis 中 fields > 0
5. 如果任何步骤失败，参考上述对应问题排查
