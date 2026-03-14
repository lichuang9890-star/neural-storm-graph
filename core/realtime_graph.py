"""Realtime Graph — 实时关系图谱与定位引擎。

增量更新 + 实时节点定位 + 流式变更通知 + 热力图分析。
基于 StormSkeleton 骨架数据构建实时运行态图谱。

设计哲学:
- 增量优先: 单文件变更 O(1) 更新，不触发全量重建
- 事件驱动: 文件变更 → 差分计算 → 回调通知
- 定位算法: 给定光标位置，实时返回符号上下文 + 调用链 + 影响范围
- 热力图: 基于变更频率 + 引用密度 + 最近修改度的可视化权重
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .storm_skeleton import StormSkeleton, SymbolDef, EdgeRef, _PY_EXTS, _TS_EXTS


# ─── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class CursorPosition:
    """光标/编辑器位置。"""
    file: str       # 相对路径
    line: int       # 1-based
    column: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "column": self.column}


@dataclass
class LocationContext:
    """实时定位上下文 — 光标所在位置的完整语义信息。"""
    cursor: CursorPosition
    symbol: SymbolDef | None = None             # 当前所在符号
    parent_scope: SymbolDef | None = None       # 父作用域符号
    callers: list[dict[str, Any]] = field(default_factory=list)     # 谁调用了当前符号
    callees: list[dict[str, Any]] = field(default_factory=list)     # 当前符号调用了谁
    siblings: list[dict[str, Any]] = field(default_factory=list)    # 同层级兄弟符号
    file_context: dict[str, Any] = field(default_factory=dict)     # 文件级上下文
    breadcrumb: list[str] = field(default_factory=list)             # 导航面包屑

    def to_dict(self) -> dict[str, Any]:
        return {
            "cursor": self.cursor.to_dict(),
            "symbol": self.symbol.to_dict() if self.symbol else None,
            "parent_scope": self.parent_scope.to_dict() if self.parent_scope else None,
            "callers": self.callers,
            "callees": self.callees,
            "siblings": self.siblings,
            "file_context": self.file_context,
            "breadcrumb": self.breadcrumb,
        }


@dataclass
class FileChange:
    """文件变更事件。"""
    file: str                # 相对路径
    kind: str                # created | modified | deleted
    timestamp: float = 0.0
    old_symbols: list[str] = field(default_factory=list)  # 变更前的 fqn 列表
    new_symbols: list[str] = field(default_factory=list)  # 变更后的 fqn 列表
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "kind": self.kind,
            "timestamp": self.timestamp,
            "added": self.added, "removed": self.removed,
            "modified": self.modified,
        }


@dataclass
class HeatmapEntry:
    """热力图节点。"""
    file: str
    heat: float = 0.0               # 综合热度 0-1
    change_freq: int = 0            # 变更次数
    ref_density: int = 0            # 引用密度（符号被引用总次数）
    recency: float = 0.0            # 最近修改度 0-1
    symbols_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "heat": round(self.heat, 4),
            "change_freq": self.change_freq,
            "ref_density": self.ref_density,
            "recency": round(self.recency, 4),
            "symbols_count": self.symbols_count,
        }


# ─── 实时图谱引擎 ──────────────────────────────────────────────────────────

ChangeCallback = Callable[[FileChange], None]


class RealtimeGraph:
    """实时关系图谱引擎 — 增量更新 + 定位 + 热力图 + 事件通知。

    Usage::

        skeleton = StormSkeleton("/project")
        skeleton.skeleton_scan()

        graph = RealtimeGraph(skeleton)
        ctx = graph.locate(CursorPosition("src/main.py", 42))
        heatmap = graph.heatmap()
        graph.on_change(my_callback)
        graph.update_file("src/main.py")
    """

    def __init__(self, skeleton: StormSkeleton) -> None:
        self.skeleton = skeleton
        self._change_log: list[FileChange] = []       # 变更历史
        self._change_freq: dict[str, int] = defaultdict(int)  # file → change count
        self._callbacks: list[ChangeCallback] = []
        self._snapshot: dict[str, list[str]] = {}      # file → [fqn] snapshot for diff
        self._lock: asyncio.Lock | None = None  # 懒初始化，仅在 async 上下文使用

        # 初始化快照
        for f, fqns in skeleton.file_symbols.items():
            self._snapshot[f] = list(fqns)

    # ─── 实时定位 API ──────────────────────────────────────────────────

    def locate(self, pos: CursorPosition) -> LocationContext:
        """实时定位 — 给定光标位置，返回完整语义上下文。

        O(n) 其中 n 是文件内符号数（通常 < 100），实际体感即时。
        """
        ctx = LocationContext(cursor=pos)
        sk = self.skeleton

        # ── 定位当前符号 ──
        file_fqns = sk.file_symbols.get(pos.file, [])
        best_sym: SymbolDef | None = None
        best_distance = float("inf")

        for fqn in file_fqns:
            sym = sk.symbols.get(fqn)
            if not sym:
                continue
            # 光标在该符号范围内
            if sym.line <= pos.line <= (sym.end_line or sym.line):
                distance = pos.line - sym.line
                if distance < best_distance:
                    best_distance = distance
                    best_sym = sym

        ctx.symbol = best_sym

        # ── 父作用域 ──
        if best_sym and best_sym.scope != "<module>":
            for fqn in file_fqns:
                s = sk.symbols.get(fqn)
                if s and s.name == best_sym.scope:
                    ctx.parent_scope = s
                    break

        # ── 调用者 (callers) ──
        if best_sym:
            for edge in sk.reverse_edges.get(best_sym.fqn, []):
                caller_sym = sk.symbols.get(edge.source)
                ctx.callers.append({
                    "fqn": edge.source,
                    "kind": edge.kind,
                    "line": edge.line,
                    "file": edge.file,
                    "symbol": caller_sym.to_dict() if caller_sym else None,
                })

        # ── 被调用者 (callees) ──
        if best_sym:
            for edge in sk.edges.get(best_sym.fqn, []):
                callee_sym = sk.symbols.get(edge.target)
                ctx.callees.append({
                    "fqn": edge.target,
                    "kind": edge.kind,
                    "line": edge.line,
                    "file": edge.file,
                    "symbol": callee_sym.to_dict() if callee_sym else None,
                })

        # ── 同层兄弟符号 ──
        if best_sym:
            for fqn in file_fqns:
                s = sk.symbols.get(fqn)
                if s and s != best_sym and s.scope == best_sym.scope:
                    ctx.siblings.append(s.to_dict())

        # ── 文件级上下文 ──
        ctx.file_context = sk.file_overview(pos.file)

        # ── 面包屑导航 ──
        crumbs = [pos.file]
        if best_sym:
            if best_sym.scope != "<module>":
                crumbs.append(best_sym.scope)
            crumbs.append(best_sym.name)
        ctx.breadcrumb = crumbs

        return ctx

    def locate_symbol(self, fqn: str) -> LocationContext | None:
        """通过 FQN 直接定位符号。"""
        sym = self.skeleton.symbols.get(fqn)
        if not sym:
            return None
        return self.locate(CursorPosition(file=sym.file, line=sym.line))

    def trace_call_chain(
        self,
        fqn: str,
        direction: str = "both",
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """追踪调用链 — 从给定符号向上/下游展开。

        Args:
            fqn: 起始符号 FQN。
            direction: "callers" | "callees" | "both"
            max_depth: 最大追踪深度。

        Returns:
            上下游调用链树。
        """
        sk = self.skeleton
        if fqn not in sk.symbols:
            return {"error": f"symbol not found: {fqn}"}

        result: dict[str, Any] = {"fqn": fqn, "symbol": sk.symbols[fqn].to_dict()}

        if direction in ("callers", "both"):
            result["callers_chain"] = self._trace_direction(
                fqn, "reverse", max_depth,
            )

        if direction in ("callees", "both"):
            result["callees_chain"] = self._trace_direction(
                fqn, "forward", max_depth,
            )

        return result

    def _trace_direction(
        self, fqn: str, direction: str, max_depth: int,
    ) -> list[dict[str, Any]]:
        """递归追踪单方向调用链。"""
        sk = self.skeleton
        visited: set[str] = {fqn}

        def _recurse(current: str, depth: int) -> list[dict[str, Any]]:
            if depth >= max_depth:
                return []
            edges = (
                sk.reverse_edges.get(current, [])
                if direction == "reverse"
                else sk.edges.get(current, [])
            )
            chain = []
            for edge in edges:
                target = edge.source if direction == "reverse" else edge.target
                if target in visited:
                    chain.append({"fqn": target, "cycle": True})
                    continue
                visited.add(target)
                sym = sk.symbols.get(target)
                node: dict[str, Any] = {
                    "fqn": target,
                    "kind": edge.kind,
                    "line": edge.line,
                    "file": edge.file,
                    "symbol": sym.to_dict() if sym else None,
                }
                children = _recurse(target, depth + 1)
                if children:
                    node["children"] = children
                chain.append(node)
            return chain

        return _recurse(fqn, 0)

    # ─── 增量更新 API ──────────────────────────────────────────────────

    def update_file(self, rel_path: str, content: str | None = None) -> FileChange:
        """增量更新单文件 — 差分计算 + 通知。

        Args:
            rel_path: 文件相对路径。
            content: 文件内容（不传则从磁盘读取）。

        Returns:
            FileChange 事件，包含 added/removed/modified 符号列表。
        """
        sk = self.skeleton
        full_path = sk.project_dir / rel_path

        # 保存旧快照
        old_fqns = set(self._snapshot.get(rel_path, []))

        # 清除该文件的旧数据
        self._purge_file(rel_path)

        # 判断事件类型
        if not full_path.exists() and content is None:
            change = FileChange(
                file=rel_path, kind="deleted",
                timestamp=time.time(),
                old_symbols=list(old_fqns),
                removed=list(old_fqns),
            )
        else:
            # 读取内容
            if content is None:
                content = full_path.read_text(encoding="utf-8", errors="replace")

            # 重新扫描
            ext = Path(rel_path).suffix
            if ext in _PY_EXTS:
                sk._regex_scan_python(rel_path, content)
                # 尝试 AST 精确模式
                try:
                    sk.deep_scan([rel_path])
                except Exception:  # noqa: BLE001
                    pass
            elif ext in _TS_EXTS:
                sk._regex_scan_ts(rel_path, content)

            # 缓存 mtime
            if full_path.exists():
                try:
                    sk._file_mtimes[rel_path] = full_path.stat().st_mtime
                except OSError:
                    pass

            # 计算差分
            new_fqns = set(sk.file_symbols.get(rel_path, []))
            added = list(new_fqns - old_fqns)
            removed = list(old_fqns - new_fqns)
            # 同名但 line 变了 → modified
            modified = []
            for fqn in new_fqns & old_fqns:
                # 简单标记为 modified（细粒度 diff 可后续扩展）
                modified.append(fqn)

            kind = "created" if not old_fqns else "modified"
            change = FileChange(
                file=rel_path, kind=kind,
                timestamp=time.time(),
                old_symbols=list(old_fqns),
                new_symbols=list(new_fqns),
                added=added, removed=removed, modified=modified,
            )

        # 更新快照
        self._snapshot[rel_path] = list(sk.file_symbols.get(rel_path, []))

        # 记录历史
        self._change_log.append(change)
        self._change_freq[rel_path] += 1

        # 限制历史长度
        if len(self._change_log) > 1000:
            self._change_log = self._change_log[-500:]

        # 触发回调
        for cb in self._callbacks:
            try:
                cb(change)
            except Exception:  # noqa: BLE001
                pass

        return change

    async def update_file_async(self, rel_path: str, content: str | None = None) -> FileChange:
        """异步版本的增量更新（线程安全）。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            return await asyncio.to_thread(self.update_file, rel_path, content)

    def batch_update(self, rel_paths: list[str]) -> list[FileChange]:
        """批量增量更新多个文件。"""
        changes = []
        for rp in rel_paths:
            changes.append(self.update_file(rp))
        return changes

    def _purge_file(self, rel_path: str) -> None:
        """清除文件的所有符号和边数据。"""
        sk = self.skeleton
        old_fqns = list(sk.file_symbols.get(rel_path, []))

        for fqn in old_fqns:
            # 删除符号
            sk.symbols.pop(fqn, None)
            # 删除正向边
            for edge in list(sk.edges.get(fqn, [])):
                sk.reverse_edges.get(edge.target, [])
                rev_list = sk.reverse_edges.get(edge.target, [])
                sk.reverse_edges[edge.target] = [
                    e for e in rev_list if e.source != fqn
                ]
            sk.edges.pop(fqn, None)
            # 删除反向边
            for edge in list(sk.reverse_edges.get(fqn, [])):
                fwd_list = sk.edges.get(edge.source, [])
                sk.edges[edge.source] = [
                    e for e in fwd_list if e.target != fqn
                ]
            sk.reverse_edges.pop(fqn, None)

        sk.file_symbols.pop(rel_path, None)
        sk.file_imports.pop(rel_path, None)

    # ─── 热力图 API ────────────────────────────────────────────────────

    def heatmap(self, top_n: int = 20) -> list[dict[str, Any]]:
        """生成文件热力图 — 基于变更频率 + 引用密度 + 时间近度。

        Returns:
            按热度排序的文件列表。
        """
        sk = self.skeleton
        now = time.time()
        max_age = 30 * 86400  # 30 days cap
        entries: list[HeatmapEntry] = []

        max_freq = max(self._change_freq.values()) if self._change_freq else 1
        max_ref = 1

        # 第一遍: 计算原始值
        raw_data: list[tuple[str, int, int, float, int]] = []
        for rel_path, fqns in sk.file_symbols.items():
            freq = self._change_freq.get(rel_path, 0)
            ref_density = sum(
                len(sk.reverse_edges.get(fqn, []))
                for fqn in fqns
            )
            if ref_density > max_ref:
                max_ref = ref_density
            mtime = sk._file_mtimes.get(rel_path, 0)
            age = now - mtime if mtime else max_age
            recency = max(0.0, 1.0 - age / max_age)
            raw_data.append((rel_path, freq, ref_density, recency, len(fqns)))

        # 第二遍: 归一化 + 综合评分
        for rel_path, freq, ref_density, recency, sym_count in raw_data:
            norm_freq = freq / max_freq if max_freq else 0
            norm_ref = ref_density / max_ref if max_ref else 0
            heat = 0.35 * norm_freq + 0.35 * norm_ref + 0.30 * recency
            entries.append(HeatmapEntry(
                file=rel_path,
                heat=heat,
                change_freq=freq,
                ref_density=ref_density,
                recency=recency,
                symbols_count=sym_count,
            ))

        entries.sort(key=lambda e: e.heat, reverse=True)
        return [e.to_dict() for e in entries[:top_n]]

    # ─── 事件订阅 ─────────────────────────────────────────────────────

    def on_change(self, callback: ChangeCallback) -> None:
        """注册文件变更回调。"""
        self._callbacks.append(callback)

    def off_change(self, callback: ChangeCallback) -> None:
        """移除文件变更回调。"""
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    # ─── 查询 API ──────────────────────────────────────────────────────

    def search_symbols(
        self,
        query: str,
        kind: str | None = None,
        file_pattern: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """搜索符号 — 模糊匹配名称 + 可选类型/文件过滤。"""
        query_lower = query.lower()
        results: list[tuple[float, SymbolDef]] = []

        for fqn, sym in self.skeleton.symbols.items():
            if kind and sym.kind != kind:
                continue
            if file_pattern and file_pattern not in sym.file:
                continue

            # 评分: 完全匹配 > 前缀匹配 > 包含匹配
            name_lower = sym.name.lower()
            if name_lower == query_lower:
                score = 1.0
            elif name_lower.startswith(query_lower):
                score = 0.8
            elif query_lower in name_lower:
                score = 0.5
            elif query_lower in fqn.lower():
                score = 0.3
            else:
                continue

            results.append((score, sym))

        results.sort(key=lambda x: x[0], reverse=True)
        return [
            {**s.to_dict(), "score": round(sc, 2)}
            for sc, s in results[:limit]
        ]

    def recent_changes(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取最近的文件变更事件。"""
        return [c.to_dict() for c in reversed(self._change_log[-limit:])]

    def dependency_graph(self, rel_path: str, depth: int = 2) -> dict[str, Any]:
        """生成文件级依赖图（import 关系）。

        Args:
            rel_path: 起始文件。
            depth: 展开深度。

        Returns:
            nodes + edges 的图结构数据。
        """
        sk = self.skeleton
        nodes: set[str] = set()
        edges_list: list[dict[str, str]] = []
        visited: set[str] = set()

        def _traverse(f: str, d: int) -> None:
            if d > depth or f in visited:
                return
            visited.add(f)
            nodes.add(f)
            for imp in sk.file_imports.get(f, set()):
                # 尝试解析 import 到实际文件
                resolved = self._resolve_import_to_file(imp)
                if resolved:
                    nodes.add(resolved)
                    edges_list.append({"from": f, "to": resolved, "kind": "import"})
                    _traverse(resolved, d + 1)

        _traverse(rel_path, 0)

        return {
            "root": rel_path,
            "depth": depth,
            "nodes": sorted(nodes),
            "edges": edges_list,
            "node_count": len(nodes),
            "edge_count": len(edges_list),
        }

    def _resolve_import_to_file(self, module_path: str) -> str | None:
        """将 import 模块路径解析为项目文件相对路径。"""
        # 尝试 a.b.c → a/b/c.py 或 a/b/c/__init__.py
        parts = module_path.replace(".", "/")
        for ext in [".py", "/__init__.py", ".ts", ".js", "/index.ts", "/index.js"]:
            candidate = parts + ext
            if candidate in self.skeleton.file_symbols:
                return candidate
            full = self.skeleton.project_dir / candidate
            if full.exists():
                return candidate
        return None

    # ─── 图谱快照 & 导出 ──────────────────────────────────────────────

    def export_graph(self) -> dict[str, Any]:
        """导出完整图谱数据（可用于前端可视化）。"""
        sk = self.skeleton
        nodes = [
            {**sym.to_dict(), "id": fqn}
            for fqn, sym in sk.symbols.items()
        ]
        edges = []
        for source, edge_list in sk.edges.items():
            for edge in edge_list:
                edges.append(edge.to_dict())

        return {
            "nodes": nodes,
            "edges": edges,
            "files": sorted(sk.file_symbols.keys()),
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def export_mermaid(self, rel_path: str | None = None, max_nodes: int = 30) -> str:
        """导出 Mermaid 流程图（可直接嵌入 Markdown）。"""
        sk = self.skeleton
        lines = ["graph LR"]
        node_ids: dict[str, str] = {}
        counter = 0

        def _node_id(fqn: str) -> str:
            nonlocal counter
            if fqn not in node_ids:
                counter += 1
                node_ids[fqn] = f"N{counter}"
            return node_ids[fqn]

        # 收集要展示的符号
        if rel_path:
            fqns = sk.file_symbols.get(rel_path, [])
        else:
            # 取中心度最高的 N 个
            centrality = {}
            for fqn in sk.symbols:
                c = len(sk.reverse_edges.get(fqn, [])) + len(sk.edges.get(fqn, []))
                centrality[fqn] = c
            sorted_fqns = sorted(centrality, key=lambda x: centrality[x], reverse=True)
            fqns = sorted_fqns[:max_nodes]

        fqn_set = set(fqns)
        for fqn in fqns:
            sym = sk.symbols.get(fqn)
            if not sym:
                continue
            nid = _node_id(fqn)
            label = sym.name
            if sym.kind == "class":
                lines.append(f"    {nid}[/{label}\\]")
            elif sym.kind == "function":
                lines.append(f"    {nid}[{label}]")
            else:
                lines.append(f"    {nid}({label})")

        for fqn in fqns:
            for edge in sk.edges.get(fqn, []):
                if edge.target in fqn_set:
                    src = _node_id(fqn)
                    tgt = _node_id(edge.target)
                    lines.append(f"    {src} --> {tgt}")

        return "\n".join(lines)

    # ─── 统计信息 ──────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """实时图谱统计。"""
        return {
            **self.skeleton.stats(),
            "change_log_size": len(self._change_log),
            "files_ever_changed": len(self._change_freq),
            "callbacks_registered": len(self._callbacks),
            "snapshot_files": len(self._snapshot),
        }
