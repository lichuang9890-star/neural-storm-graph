#!/usr/bin/env python3
"""一键运行全部领域案例 + 汇总 Benchmark"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Neural Storm Graph — 领域案例 Benchmark                ║")
    print("║  风暴骨架 + 实时图谱 在多领域的实测表现                 ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    from traffic_network import run_demo as traffic_demo
    from crime_network import run_demo as crime_demo
    from finance_aml import run_demo as finance_demo

    traffic_demo()
    crime_demo()
    finance_demo()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ✅ 全部案例运行完毕                                   ║")
    print("║  Zero Dependencies · Pure Python · < 1s per scenario    ║")
    print("╚══════════════════════════════════════════════════════════╝")
