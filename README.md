# Neural Storm Graph ⚡

> "风暴、骨架、实时。" — The philosophy of Neural Storm Graph.

A hyper-modular, real-time relationship graph engine powered by the Storm Skeleton protocol. Designed for dynamic context extraction and AI memory structuring without the bloat of traditional dashboards.

## 核心特性 (Features)

- ⚡ **实时图谱 (Real-time Graph):** Construct relationship graphs instantly via semantic abstraction.
- 🦴 **风暴骨架 (Storm Skeleton):** The absolute bare-minimum execution framework for maximum performance and boundless AI context iteration.
- 🛡️ **纯净无感 (Zero-Bloat):** Strictly focused on memory mapping and node logic. No UI overhead.
- 🎯 **实时定位 (Real-time Positioning):** Cursor-aware context engine — knows exactly where you are in the codebase.

## 目录结构 (Structure)

```text
neural-storm-graph/
├── core/
│   ├── __init__.py          # 包入口
│   ├── storm_skeleton.py    # 风暴骨架引擎（调度、推理、骨架扫描）
│   └── realtime_graph.py    # 实时网络流与关系节点提取算法
├── test_storm.py            # 完整测试套件 (45 tests)
├── requirements.txt
└── README.md
```

## 功能矩阵 (Feature Matrix)

### Storm Skeleton — 骨架引擎

| API | 功能 | 复杂度 |
|-----|------|--------|
| `skeleton_scan()` | 极速正则骨架扫描，对 SyntaxError 完全容错 | O(files) |
| `deep_scan()` | AST 精确模式，自动降级到正则 | O(files × AST) |
| `storm_center()` | 风暴中心多维定位（关键词+中心度+复杂度+时间） | O(symbols) |
| `decompose()` | DAG 依赖推理 + 循环检测 + 层级任务 ID | O(V+E) |
| `impact_analysis()` | BFS 影响范围分析 | O(V+E) |
| `file_overview()` | 单文件骨架概览 | O(1) |
| `get_snippet()` | 符号源码片段 | O(1) |

### Realtime Graph — 实时图谱 + 定位

| API | 功能 | 复杂度 |
|-----|------|--------|
| `locate()` | 实时光标定位（符号+调用者+被调用者+兄弟+面包屑） | O(n) file symbols |
| `locate_symbol()` | 通过 FQN 直接定位 | O(n) |
| `trace_call_chain()` | 上下游调用链追踪 | O(V+E) |
| `update_file()` | 增量单文件更新 + 差分计算 + 事件通知 | O(1) |
| `batch_update()` | 批量增量更新 | O(files) |
| `heatmap()` | 文件热力图（变更频率+引用密度+时间） | O(files) |
| `search_symbols()` | 模糊符号搜索 + 类型/文件过滤 | O(symbols) |
| `dependency_graph()` | 文件级依赖图（BFS展开） | O(V+E) |
| `export_graph()` | 导出全量节点+边（JSON，前端可视化用） | O(V+E) |
| `export_mermaid()` | 导出 Mermaid 流程图（Markdown 嵌入） | O(V+E) |
| `on_change()` / `off_change()` | 文件变更事件订阅/取消 | O(1) |

## Quick Start

```python
from core import StormSkeleton, RealtimeGraph
from core.realtime_graph import CursorPosition

# 1. 骨架扫描
skeleton = StormSkeleton("/path/to/your/project")
report = skeleton.skeleton_scan()
print(f"Scanned {report['files_scanned']} files, "
      f"{report['total_symbols']} symbols in {report['scan_time_ms']}ms")

# 2. 风暴中心定位 — 找到项目中最相关的核心节点
center = skeleton.storm_center("修复限流中间件")
for node in center["top_nodes"][:5]:
    print(f"  {node['fqn']} (score: {node['total']})")

# 3. DAG 依赖推理
dag = skeleton.decompose("重构用户服务")
print(f"Decomposed into {dag['total_nodes']} nodes, cycles: {dag['cycles']}")

# 4. 实时图谱 + 光标定位
graph = RealtimeGraph(skeleton)
ctx = graph.locate(CursorPosition("src/middleware.py", 42))
print(f"Symbol: {ctx.symbol.name if ctx.symbol else 'N/A'}")
print(f"Callers: {len(ctx.callers)}, Callees: {len(ctx.callees)}")
print(f"Breadcrumb: {' > '.join(ctx.breadcrumb)}")

# 5. 增量更新 + 事件监听
graph.on_change(lambda c: print(f"[CHANGE] {c.file}: +{len(c.added)} -{len(c.removed)}"))
change = graph.update_file("src/middleware.py")

# 6. 热力图
for entry in graph.heatmap()[:5]:
    print(f"  {entry['file']}: heat={entry['heat']}")

# 7. 调用链追踪
chain = graph.trace_call_chain("src/main.py::App.run", direction="both")

# 8. 导出 Mermaid 图
print(graph.export_mermaid(rel_path="src/main.py"))
```

## 零依赖 (Zero Dependencies)

纯 Python stdlib 实现，无需安装任何外部包。Python >= 3.10。

## 测试 (Testing)

```bash
python -m pytest test_storm.py -v   # 45/45 tests, < 1s
```

## 设计哲学 (Philosophy)

- **正则优先，AST 辅助**: 骨架扫描用正则——即使文件有语法错误也不中断。AST 仅在需要精确调用链时启用。
- **增量优先**: 单文件变更 O(1) 更新，不触发全量重建。
- **事件驱动**: 文件变更 → 差分计算 → 回调通知。
- **多维评分**: 风暴中心不是简单的文本搜索，而是结合关键词、中心度、复杂度、时间的四维评分。

> 剔除一切华而不实的呈现层，保留最纯粹的数据引擎心脏。风暴即思考，图谱即记忆。
