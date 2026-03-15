#!/usr/bin/env python3
"""金融风控反洗钱分析 — Neural Storm Graph 领域案例 #3

场景: 银行账户作为节点，转账记录作为边，
     storm_center 定位可疑枢纽账户，
     trace_call_chain 追踪资金流转链路，
     decompose 输出风控排查优先级。

演示: 生成 300 账户 + 800 笔交易的模拟金融网络。
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

BANKS = ["icbc", "ccb", "abc", "boc", "cmb", "spdb"]


def generate_finance_network(base_dir: str, n_accounts: int = 300, n_transactions: int = 800) -> None:
    """生成模拟金融交易网络。"""
    random.seed(2025)
    os.makedirs(os.path.join(base_dir, "banks"), exist_ok=True)

    all_accounts: list[tuple[str, str]] = []
    per_bank = n_accounts // len(BANKS)

    for b_idx, bank in enumerate(BANKS):
        filepath = os.path.join(base_dir, "banks", f"{bank}.py")
        lines = [
            f'"""银行: {bank.upper()} — 账户节点"""',
            "from __future__ import annotations",
            "",
        ]
        for i in range(per_bank):
            idx = b_idx * per_bank + i
            acct = f"Account_{idx:04d}"
            balance = random.randint(1000, 10_000_000)
            risk = random.uniform(0, 1.0)
            lines.extend([
                f"class {acct}:",
                f'    \"\"\"账户 {idx} | 余额: ¥{balance:,} | 风险: {risk:.2f}\"\"\"',
                f"    balance = {balance}",
                f"    risk_flag = {risk:.2f}",
                "",
                f"    def deposit(self, amount: float) -> None:",
                f'        \"\"\"入账\"\"\"',
                f"        self.balance += amount",
                "",
                f"    def withdraw(self, amount: float) -> None:",
                f'        \"\"\"出账\"\"\"',
                f"        self.balance -= amount",
                "",
                f"    def freeze(self) -> None:",
                f'        \"\"\"冻结账户\"\"\"',
                f"        pass",
                "",
            ])
            all_accounts.append((bank, acct))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # 交易记录
    tx_lines = [
        '"""交易流水 — 账户间转账记录"""',
        "from __future__ import annotations",
        "",
    ]
    for bank in BANKS:
        tx_lines.append(f"from banks.{bank} import *")
    tx_lines.append("")

    edges = 0
    for _ in range(n_transactions):
        src = random.choice(all_accounts)
        dst = random.choice(all_accounts)
        if src == dst:
            continue
        amount = random.choice([
            random.randint(100, 5000),          # 小额
            random.randint(50000, 500000),       # 大额
            random.randint(999000, 1000000),     # 临界值（可疑）
        ])
        fn = f"tx_{src[1].lower()}_to_{dst[1].lower()}_{edges}"
        tx_lines.extend([
            f"def {fn}():",
            f'    \"\"\"转账 ¥{amount:,}: {src[1]} → {dst[1]}\"\"\"',
            f"    sender = {src[1]}()",
            f"    receiver = {dst[1]}()",
            f"    sender.withdraw({amount})",
            f"    receiver.deposit({amount})",
            "",
        ])
        edges += 1

    with open(os.path.join(base_dir, "transactions.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(tx_lines))

    # 风控中心
    main_lines = [
        '"""风控监测中心"""',
        "from __future__ import annotations",
        "from transactions import *",
        "",
        "class RiskCenter:",
        '    """反洗钱风控中心"""',
        "",
        "    def detect_circular_flow(self) -> list:",
        '        """检测循环转账（洗钱环路）"""',
        "        return []",
        "",
        "    def suspicious_report(self) -> dict:",
        '        """生成可疑交易报告"""',
        "        return {}",
        "",
        "    def freeze_chain(self, account: str) -> int:",
        '        """冻结关联账户链"""',
        "        return 0",
        "",
    ]
    with open(os.path.join(base_dir, "risk_center.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(main_lines))

    print(f"  ✓ 生成完毕: {n_accounts} 账户, {edges} 笔交易, {len(BANKS)} 家银行")


def run_demo() -> None:
    """运行金融风控分析演示。"""
    print("=" * 60)
    print("  💰 金融风控反洗钱分析")
    print("  Neural Storm Graph — 领域案例 #3")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. 生成网络
        print("\n[1/5] 生成模拟金融交易网络...")
        t0 = time.perf_counter()
        generate_finance_network(tmpdir)
        gen_ms = (time.perf_counter() - t0) * 1000
        print(f"       → {gen_ms:.1f}ms")

        # 2. 骨架扫描
        print("\n[2/5] 骨架扫描 — 识别所有账户/交易...")
        t0 = time.perf_counter()
        skeleton = StormSkeleton(tmpdir)
        report = skeleton.skeleton_scan()
        scan_ms = (time.perf_counter() - t0) * 1000
        print(f"  ✓ {report['files_scanned']} 文件 | {report['total_symbols']} 符号 | {report['total_edges']} 边")
        print(f"       → {scan_ms:.1f}ms")

        # 3. 风暴中心 — 定位可疑枢纽
        print("\n[3/5] 风暴中心 — 定位可疑资金枢纽...")
        t0 = time.perf_counter()
        center = skeleton.storm_center("withdraw deposit freeze risk suspicious transfer")
        center_ms = (time.perf_counter() - t0) * 1000
        print(f"  Top 5 可疑枢纽:")
        for node in center["top_nodes"][:5]:
            print(f"    🔴 {node['fqn']} (score: {node['total']:.1f})")
        print(f"       → {center_ms:.1f}ms")

        # 4. DAG 分解 — 风控排查
        print("\n[4/5] DAG 推理 — 风控排查任务分解...")
        t0 = time.perf_counter()
        dag = skeleton.decompose("反洗钱排查冻结")
        decompose_ms = (time.perf_counter() - t0) * 1000
        print(f"  ✓ {dag['total_nodes']} 个排查任务 | 循环: {len(dag['cycles'])} 个环")
        for task in dag["tree"][:3]:
            print(f"    📋 [{task['task_id']}] {task['fqn']} (depth: {task['depth']})")
        print(f"       → {decompose_ms:.1f}ms")

        # 5. 实时定位 — 定位到具体银行
        print("\n[5/5] 实时图谱 — 定位到 ICBC 分行...")
        t0 = time.perf_counter()
        graph = RealtimeGraph(skeleton)
        ctx = graph.locate(CursorPosition("banks/icbc.py", 15))
        locate_ms = (time.perf_counter() - t0) * 1000
        if ctx.symbol:
            print(f"  ✓ 当前账户: {ctx.symbol.name}")
            print(f"    关联入账: {len(ctx.callers)} | 关联出账: {len(ctx.callees)}")
            print(f"    路径: {' > '.join(ctx.breadcrumb)}")
        print(f"       → {locate_ms:.1f}ms")

        total_ms = gen_ms + scan_ms + center_ms + decompose_ms + locate_ms
        print("\n" + "=" * 60)
        print("  📊 性能汇总")
        print("=" * 60)
        print(f"  网络生成:     {gen_ms:>8.1f}ms")
        print(f"  骨架扫描:     {scan_ms:>8.1f}ms")
        print(f"  枢纽定位:     {center_ms:>8.1f}ms")
        print(f"  任务分解:     {decompose_ms:>8.1f}ms")
        print(f"  实时定位:     {locate_ms:>8.1f}ms")
        print(f"  ─────────────────────────")
        print(f"  总耗时:       {total_ms:>8.1f}ms")
        print()


if __name__ == "__main__":
    run_demo()
