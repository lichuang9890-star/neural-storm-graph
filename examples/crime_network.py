#!/usr/bin/env python3
"""犯罪关系网络分析 — Neural Storm Graph 领域案例 #2

场景: 嫌疑人作为节点，关联关系（通话、转账、同行）作为边，
     storm_center 定位核心嫌疑人，decompose 分解侦查任务，
     trace_call_chain 追踪犯罪链条。

演示: 生成 150 人 + 400 条关系的模拟犯罪网络。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import StormSkeleton, RealtimeGraph
from core.realtime_graph import CursorPosition


GANGS = ["tiger", "dragon", "shadow", "iron", "ghost"]
RELATION_TYPES = ["phone_call", "money_transfer", "meeting", "message", "travel_together"]


def generate_crime_network(base_dir: str, n_suspects: int = 150, n_relations: int = 400) -> None:
    """生成模拟犯罪关系网络。

    每个嫌疑人 = class，每条关系 = 函数调用。
    """
    random.seed(2024)
    os.makedirs(os.path.join(base_dir, "gangs"), exist_ok=True)

    all_suspects: list[tuple[str, str]] = []  # (gang, class_name)

    suspects_per_gang = n_suspects // len(GANGS)

    for g_idx, gang in enumerate(GANGS):
        filepath = os.path.join(base_dir, "gangs", f"{gang}.py")
        lines = [
            f'"""团伙: {gang} — 嫌疑人节点"""',
            "from __future__ import annotations",
            "",
        ]
        for i in range(suspects_per_gang):
            idx = g_idx * suspects_per_gang + i
            cls = f"Suspect_{idx:03d}"
            risk = random.uniform(0.1, 1.0)
            lines.extend([
                f"class {cls}:",
                f'    \"\"\"嫌疑人 {idx} | 危险度: {risk:.2f} | 团伙: {gang}\"\"\"',
                f"    risk_score = {risk:.2f}",
                f'    gang = "{gang}"',
                "",
                f"    def contact(self, target: str) -> None:",
                f'        \"\"\"与目标联络\"\"\"',
                f"        pass",
                "",
                f"    def transfer_money(self, amount: float) -> None:",
                f'        \"\"\"资金转移\"\"\"',
                f"        pass",
                "",
            ])
            all_suspects.append((gang, cls))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # 关系文件
    rel_lines = [
        '"""关系网络 — 嫌疑人之间的关联"""',
        "from __future__ import annotations",
        "",
    ]
    for gang in GANGS:
        rel_lines.append(f"from gangs.{gang} import *")
    rel_lines.append("")

    edges = 0
    for _ in range(n_relations):
        src = random.choice(all_suspects)
        dst = random.choice(all_suspects)
        if src == dst:
            continue
        rel_type = random.choice(RELATION_TYPES)
        fn = f"rel_{rel_type}_{src[1].lower()}_to_{dst[1].lower()}"
        rel_lines.extend([
            f"def {fn}():",
            f'    \"\"\"[{rel_type}] {src[1]} → {dst[1]}\"\"\"',
            f"    a = {src[1]}()",
            f"    b = {dst[1]}()",
            f"    a.contact('{dst[1]}')",
            "",
        ])
        edges += 1

    with open(os.path.join(base_dir, "relations.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(rel_lines))

    # 侦查主控
    main_lines = [
        '"""侦查指挥中心"""',
        "from __future__ import annotations",
        "from relations import *",
        "",
        "class InvestigationCenter:",
        '    """案件侦查总控"""',
        "",
        "    def identify_leader(self) -> str:",
        '        """识别核心头目"""',
        '        return "unknown"',
        "",
        "    def trace_money_flow(self) -> list:",
        '        """追踪资金流向"""',
        "        return []",
        "",
        "    def arrest_plan(self) -> dict:",
        '        """制定抓捕方案"""',
        "        return {}",
        "",
    ]
    with open(os.path.join(base_dir, "investigation.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(main_lines))

    print(f"  ✓ 生成完毕: {n_suspects} 嫌疑人, {edges} 条关系, {len(GANGS)} 个团伙")


def run_demo() -> None:
    """运行犯罪关系网络分析演示。"""
    print("=" * 60)
    print("  🔍 犯罪关系网络分析")
    print("  Neural Storm Graph — 领域案例 #2")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 生成网络
        print("\n[1/5] 生成模拟犯罪网络...")
        t0 = time.perf_counter()
        generate_crime_network(tmpdir)
        gen_ms = (time.perf_counter() - t0) * 1000
        print(f"       → {gen_ms:.1f}ms")

        # 2. 骨架扫描
        print("\n[2/5] 骨架扫描 — 识别所有嫌疑人/关系...")
        t0 = time.perf_counter()
        skeleton = StormSkeleton(tmpdir)
        report = skeleton.skeleton_scan()
        scan_ms = (time.perf_counter() - t0) * 1000
        print(f"  ✓ {report['files_scanned']} 文件 | {report['total_symbols']} 符号 | {report['total_edges']} 边")
        print(f"       → {scan_ms:.1f}ms")

        # 3. 风暴中心 — 定位核心嫌疑人
        print("\n[3/5] 风暴中心 — 定位犯罪网络核心人物...")
        t0 = time.perf_counter()
        center = skeleton.storm_center("contact transfer_money risk gang leader")
        center_ms = (time.perf_counter() - t0) * 1000
        print(f"  Top 5 核心嫌疑人:")
        for node in center["top_nodes"][:5]:
            print(f"    🔴 {node['fqn']} (score: {node['total']:.1f})")
        print(f"       → {center_ms:.1f}ms")

        # 4. DAG 分解 — 侦查任务分解
        print("\n[4/5] DAG 推理 — 侦查抓捕任务分解...")
        t0 = time.perf_counter()
        dag = skeleton.decompose("侦查抓捕犯罪团伙")
        decompose_ms = (time.perf_counter() - t0) * 1000
        print(f"  ✓ {dag['total_nodes']} 个任务节点 | 循环: {len(dag['cycles'])} 个环")
        for task in dag["tree"][:3]:
            print(f"    📋 [{task['task_id']}] {task['fqn']} (depth: {task['depth']})")
        print(f"       → {decompose_ms:.1f}ms")

        # 5. 影响分析
        print("\n[5/5] 影响分析 — 抓获核心人物的连锁反应...")
        # 找一个有边的符号
        target_fqn = center["top_nodes"][0]["fqn"] if center["top_nodes"] else ""
        t0 = time.perf_counter()
        if target_fqn:
            impact = skeleton.impact_analysis(target_fqn)
            impact_ms = (time.perf_counter() - t0) * 1000
            affected = impact.get('affected', [])
            print(f"  ✓ 抓获 {target_fqn} 影响: {impact['affected_count']} 个关联节点")
            for n in affected[:3]:
                print(f"    💥 {n['fqn']} (depth: {n['depth']})")
        else:
            impact_ms = 0
            print("  ⚠ 未找到有效目标")
        print(f"       → {impact_ms:.1f}ms")

        # 汇总
        total_ms = gen_ms + scan_ms + center_ms + decompose_ms + impact_ms
        print("\n" + "=" * 60)
        print("  📊 性能汇总")
        print("=" * 60)
        print(f"  网络生成:     {gen_ms:>8.1f}ms")
        print(f"  骨架扫描:     {scan_ms:>8.1f}ms")
        print(f"  核心人物定位: {center_ms:>8.1f}ms")
        print(f"  任务分解:     {decompose_ms:>8.1f}ms")
        print(f"  影响链分析:   {impact_ms:>8.1f}ms")
        print(f"  ─────────────────────────")
        print(f"  总耗时:       {total_ms:>8.1f}ms")
        print()


if __name__ == "__main__":
    run_demo()
