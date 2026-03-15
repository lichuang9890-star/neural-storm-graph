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

## 实测 Benchmark

> 真机测试环境: Windows 11, Python 3.12, AMD Ryzen — 2026-03-15

### 代码仓库扫描 (fastapi-rate-limiter 项目)

| 指标 | 数值 |
|------|------|
| 文件 | 391 |
| 符号 | 16,208 |
| 调用边 | 23,204 |
| 骨架扫描耗时 | < 1s |
| 测试 | 45/45 pass |

### 领域案例实测

| 案例 | 节点 | 边 | 骨架扫描 | 风暴中心 | DAG分解 | 实时定位 | 总耗时 |
|------|------|----|----------|----------|---------|----------|--------|
| 🚦 交通网络 (200路口) | 1,099 | 900 | 221ms | 7.7ms | 8.9ms | 0.5ms | **242ms** |
| 🔍 犯罪关系 (150嫌疑人) | 852 | 702 | 160ms | 5.8ms | 5.8ms | 0.2ms | **176ms** |
| 💰 金融风控 (300账户) | 2,000 | 1,699 | 494ms | 16ms | 13ms | 0.2ms | **529ms** |

> 关键发现: **风暴中心定位 < 20ms**，**实时光标定位 < 1ms**，**全场景 < 1s**

## 领域应用案例

`examples/` 目录包含 3 个完整可运行的领域案例：

### 🚦 交通网络拥堵传播 (`traffic_network.py`)
- 200 路口 + 500 路段，5 个城区
- `storm_center` 定位拥堵核心路口
- `decompose` 生成疏导优先级
- `locate` 实时定位到具体路口

### 🔍 犯罪关系网络分析 (`crime_network.py`)  
- 150 嫌疑人 + 400 条关系，5 个团伙
- `storm_center` 定位核心头目
- `impact_analysis` 分析抓捕连锁反应（抓 1 人影响 149 人）
- `decompose` 规划侦查任务

### 💰 金融风控反洗钱 (`finance_aml.py`)
- 300 账户 + 800 笔交易，6 家银行
- `storm_center` 定位可疑资金枢纽
- `decompose` 输出排查优先级
- `locate` 定位到具体银行分行

```bash
# 一键运行全部案例
cd examples && python run_all.py
```

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
