#!/usr/bin/env python3
"""交通网络拥堵传播分析 — Neural Storm Graph 领域案例 #1

场景: 城市交通路口作为节点，路段作为边，使用 storm_center 定位拥堵核心，
     trace_call_chain 追踪拥堵传播链，decompose 分析依赖瓶颈。

演示: 生成 200 个路口 + 500 条路段的模拟交通网络，使用 StormSkeleton 进行分析。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import random

# 让 import 能找到 core/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import StormSkeleton, RealtimeGraph
from core.realtime_graph import CursorPosition


def generate_traffic_network(base_dir: str, n_intersections: int = 200, n_roads: int = 500) -> None:
    """生成模拟交通网络的 Python 文件结构。

    每个路口 = 一个 class，每条路段 = 一个函数调用关系。
    """
    random.seed(42)
    os.makedirs(os.path.join(base_dir, "districts"), exist_ok=True)

    # 分区: 把路口分到 5 个区
    districts = ["downtown", "eastside", "westside", "north", "south"]
    intersections_per_district = n_intersections // len(districts)

    all_intersections: list[tuple[str, str, str]] = []  # (district, class_name, file)

    for d_idx, district in enumerate(districts):
        filepath = os.path.join(base_dir, "districts", f"{district}.py")
        lines = [
            f'"""区域: {district} — 交通路口节点"""',
            "from __future__ import annotations",
            "",
        ]
        start = d_idx * intersections_per_district
        for i in range(intersections_per_district):
            idx = start + i
            cls_name = f"Intersection_{idx:03d}"
            # 拥堵权重模拟
            congestion = random.uniform(0.1, 1.0)
            throughput = random.randint(100, 5000)
            lines.extend([
                f"class {cls_name}:",
                f'    \"\"\"路口 {idx} | 拥堵系数: {congestion:.2f} | 通行量: {throughput} 辆/h\"\"\"',
                f"    congestion = {congestion:.2f}",
                f"    throughput = {throughput}",
                "",
                f"    def signal_control(self) -> str:",
                f'        return "green" if self.congestion < 0.6 else "red"',
                "",
                f"    def reroute(self) -> None:",
                f'        \"\"\"拥堵时触发重路由\"\"\"',
                f"        pass",
                "",
            ])
            all_intersections.append((district, cls_name, f"districts/{district}.py"))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # 生成路段（调用关系文件）
    road_lines = [
        '"""路段连接 — 路口之间的调用关系"""',
        "from __future__ import annotations",
        "",
    ]
    for district in districts:
        road_lines.append(f"from districts.{district} import *")
    road_lines.append("")

    edges_created = 0
    for _ in range(n_roads):
        src = random.choice(all_intersections)
        dst = random.choice(all_intersections)
        if src == dst:
            continue
        func_name = f"road_{src[1].lower()}_to_{dst[1].lower()}"
        road_lines.extend([
            f"def {func_name}():",
            f'    \"\"\"路段: {src[1]} → {dst[1]}\"\"\"',
            f"    a = {src[1]}()",
            f"    b = {dst[1]}()",
            f"    a.signal_control()",
            f"    b.reroute()",
            "",
        ])
        edges_created += 1
        if edges_created >= n_roads:
            break

    with open(os.path.join(base_dir, "roads.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(road_lines))

    # 入口文件
    main_lines = [
        '"""交通网络主控"""',
        "from __future__ import annotations",
        "from roads import *",
        "",
        "class TrafficController:",
        '    """全局交通调度中心"""',
        "",
        "    def monitor(self) -> None:",
        '        """实时监控"""',
        "        pass",
        "",
        "    def emergency_reroute(self, zone: str) -> None:",
        '        """紧急疏导"""',
        "        pass",
        "",
    ]
    with open(os.path.join(base_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(main_lines))

    print(f"  ✓ 生成完毕: {n_intersections} 路口, {edges_created} 路段, {len(districts)} 区域")


def run_demo() -> None:
    """运行完整交通网络分析演示。"""
    print("=" * 60)
    print("  🚦 交通网络拥堵传播分析")
    print("  Neural Storm Graph — 领域案例 #1")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 生成网络
        print("\n[1/5] 生成模拟交通网络...")
        t0 = time.perf_counter()
        generate_traffic_network(tmpdir, n_intersections=200, n_roads=500)
        gen_ms = (time.perf_counter() - t0) * 1000
        print(f"       → {gen_ms:.1f}ms")

        # 2. 骨架扫描
        print("\n[2/5] 骨架扫描 — 识别所有路口/路段...")
        t0 = time.perf_counter()
        skeleton = StormSkeleton(tmpdir)
        report = skeleton.skeleton_scan()
        scan_ms = (time.perf_counter() - t0) * 1000
        print(f"  ✓ {report['files_scanned']} 文件 | {report['total_symbols']} 符号 | {report['total_edges']} 边")
        print(f"       → {scan_ms:.1f}ms")

        # 3. 风暴中心 — 定位拥堵核心
        print("\n[3/5] 风暴中心定位 — 找到拥堵最严重的核心节点...")
        t0 = time.perf_counter()
        center = skeleton.storm_center("拥堵 congestion reroute signal")
        center_ms = (time.perf_counter() - t0) * 1000
        print(f"  Top 5 拥堵核心:")
        for node in center["top_nodes"][:5]:
            print(f"    ⚡ {node['fqn']} (score: {node['total']:.1f})")
        print(f"       → {center_ms:.1f}ms")

        # 4. DAG 依赖推理 — 疏导任务分解
        print("\n[4/5] DAG 依赖推理 — 拥堵疏导任务分解...")
        t0 = time.perf_counter()
        dag = skeleton.decompose("交通拥堵疏导方案")
        decompose_ms = (time.perf_counter() - t0) * 1000
        print(f"  ✓ {dag['total_nodes']} 个任务节点 | 循环检测: {len(dag['cycles'])} 个环")
        for task in dag["tree"][:3]:
            print(f"    📋 [{task['task_id']}] {task['fqn']} (depth: {task['depth']})")
        print(f"       → {decompose_ms:.1f}ms")

        # 5. 实时图谱 + 定位
        print("\n[5/5] 实时图谱 — 光标定位到 downtown 区...")
        t0 = time.perf_counter()
        graph = RealtimeGraph(skeleton)
        ctx = graph.locate(CursorPosition("districts/downtown.py", 10))
        locate_ms = (time.perf_counter() - t0) * 1000
        if ctx.symbol:
            print(f"  ✓ 当前符号: {ctx.symbol.name}")
            print(f"    调用者: {len(ctx.callers)} | 被调用者: {len(ctx.callees)}")
            print(f"    面包屑: {' > '.join(ctx.breadcrumb)}")
        print(f"       → {locate_ms:.1f}ms")

        # 汇总
        total_ms = gen_ms + scan_ms + center_ms + decompose_ms + locate_ms
        print("\n" + "=" * 60)
        print("  📊 性能汇总")
        print("=" * 60)
        print(f"  网络生成:     {gen_ms:>8.1f}ms")
        print(f"  骨架扫描:     {scan_ms:>8.1f}ms")
        print(f"  风暴中心定位: {center_ms:>8.1f}ms")
        print(f"  DAG 任务分解: {decompose_ms:>8.1f}ms")
        print(f"  实时光标定位: {locate_ms:>8.1f}ms")
        print(f"  ─────────────────────────")
        print(f"  总耗时:       {total_ms:>8.1f}ms")
        print()


if __name__ == "__main__":
    run_demo()
