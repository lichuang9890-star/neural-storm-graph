"""Storm Skeleton — 风暴骨架引擎。

极速代码骨架扫描 + 多维风暴中心定位 + DAG 依赖推理。
零外部依赖，纯 stdlib，对语法错误完全容错（正则优先，AST 辅助）。

设计哲学:
- 骨架扫描使用正则，即使文件有 SyntaxError 也不会中断
- AST 仅在正则无法满足精度时启用（双模式降级）
- 风暴中心通过多维打分定位项目中"最重要"的节点
- 所有数据结构使用原生 dict/list，序列化零成本
"""
from __future__ import annotations

import ast
import math
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── 常量 ───────────────────────────────────────────────────────────────────

_PY_DEF_RE = re.compile(
    r"^(?P<indent>\s*)(?:async\s+)?(?P<kind>def|class)\s+(?P<name>\w+)",
    re.MULTILINE,
)
_PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?P<from>[\w.]+)\s+import\s+(?P<names>[^#\n]+)"
    r"|import\s+(?P<imp>[\w., ]+))",
    re.MULTILINE,
)
_PY_CALL_RE = re.compile(r"\b(?P<callee>\w+(?:\.\w+)*)\s*\(")
_PY_DECORATOR_RE = re.compile(r"^\s*@(?P<dec>\w+(?:\.\w+)*)", re.MULTILINE)

_TS_DEF_RE = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?P<kind>function|class|interface|type|enum|const|let|var)"
    r"\s+(?P<name>\w+)",
    re.MULTILINE,
)
_TS_IMPORT_RE = re.compile(
    r"""import\s+(?:\{[^}]*\}|[\w*]+(?:\s+as\s+\w+)?)\s+from\s+['"](?P<mod>[^'"]+)['"]""",
    re.MULTILINE,
)

_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", "egg-info",
}
_PY_EXTS = {".py", ".pyi"}
_TS_EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
_ALL_EXTS = _PY_EXTS | _TS_EXTS


# ─── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class SymbolDef:
    """单个符号定义（函数 / 类 / 变量 / 接口 …）。"""
    name: str
    kind: str                          # function | class | variable | interface | type | enum
    file: str                          # 相对路径
    line: int
    end_line: int = 0
    scope: str = "<module>"            # 父作用域
    args: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)

    @property
    def fqn(self) -> str:
        """Fully qualified name: file::scope.name."""
        if self.scope == "<module>":
            return f"{self.file}::{self.name}"
        return f"{self.file}::{self.scope}.{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "file": self.file,
            "line": self.line, "end_line": self.end_line, "scope": self.scope,
            "args": self.args, "decorators": self.decorators, "bases": self.bases,
            "fqn": self.fqn,
        }


@dataclass
class EdgeRef:
    """一条从 source 到 target 的引用边。"""
    source: str              # fqn
    target: str              # fqn
    kind: str                # call | import | attr_ref | extends
    file: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "target": self.target,
            "kind": self.kind, "file": self.file, "line": self.line,
        }


@dataclass
class StormScore:
    """风暴中心多维评分。"""
    fqn: str
    keyword_score: float = 0.0         # 关键词匹配度
    centrality_score: float = 0.0      # 引用中心度（入度+出度）
    complexity_score: float = 0.0      # 代码行数 / 复杂度
    recency_score: float = 0.0         # 文件修改时间近度
    total: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fqn": self.fqn,
            "keyword": round(self.keyword_score, 4),
            "centrality": round(self.centrality_score, 4),
            "complexity": round(self.complexity_score, 4),
            "recency": round(self.recency_score, 4),
            "total": round(self.total, 4),
        }


# ─── AST 辅助访问器 ────────────────────────────────────────────────────────

class _SymbolVisitor(ast.NodeVisitor):
    """AST 精确模式 — 提取定义 + 引用 + 调用。"""

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.symbols: list[SymbolDef] = []
        self.calls: list[tuple[str, int]] = []       # (callee_name, line)
        self.imports: list[tuple[str, str, int]] = [] # (module, name, line)
        self._scope_stack: list[str] = ["<module>"]

    # ── 定义 ──

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_func(node)

    def _handle_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = [a.arg for a in node.args.args]
        decs = [self._dec_name(d) for d in node.decorator_list]
        sym = SymbolDef(
            name=node.name, kind="function", file=self.rel_path,
            line=node.lineno, end_line=node.end_lineno or node.lineno,
            scope=self._scope_stack[-1], args=args, decorators=decs,
        )
        self.symbols.append(sym)
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [self._node_name(b) for b in node.bases if self._node_name(b)]
        decs = [self._dec_name(d) for d in node.decorator_list]
        sym = SymbolDef(
            name=node.name, kind="class", file=self.rel_path,
            line=node.lineno, end_line=node.end_lineno or node.lineno,
            scope=self._scope_stack[-1], decorators=decs, bases=bases,
        )
        self.symbols.append(sym)
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    # ── 引用 ──

    def visit_Call(self, node: ast.Call) -> None:
        name = self._node_name(node.func)
        if name:
            self.calls.append((name, node.lineno))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append((alias.name, alias.asname or alias.name, node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for alias in node.names:
            self.imports.append((mod, alias.name, node.lineno))

    # ── 工具 ──

    @staticmethod
    def _node_name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = _SymbolVisitor._node_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return None

    @staticmethod
    def _dec_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = _SymbolVisitor._node_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        if isinstance(node, ast.Call):
            return _SymbolVisitor._dec_name(node.func)
        return "<unknown>"


# ─── 主引擎类 ──────────────────────────────────────────────────────────────

class StormSkeleton:
    """风暴骨架引擎 — 调度 + 骨架扫描 + 风暴中心定位 + 依赖推理。

    Usage::

        engine = StormSkeleton("/path/to/project")
        report = engine.skeleton_scan()           # 极速骨架概览
        center = engine.storm_center("修复限流")   # 风暴中心定位
        dag = engine.decompose("重构中间件")       # 依赖 DAG 推理
    """

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.symbols: dict[str, SymbolDef] = {}        # fqn → SymbolDef
        self.edges: dict[str, list[EdgeRef]] = defaultdict(list)     # source → [edges]
        self.reverse_edges: dict[str, list[EdgeRef]] = defaultdict(list)  # target → [edges]
        self.file_imports: dict[str, set[str]] = defaultdict(set)    # file → {imported files}
        self.file_symbols: dict[str, list[str]] = defaultdict(list)  # file → [fqn list]
        self._file_mtimes: dict[str, float] = {}
        self._scan_time: float = 0.0

    # ─── 公共 API ──────────────────────────────────────────────────────

    def skeleton_scan(self) -> dict[str, Any]:
        """极速骨架扫描（正则模式，完全容错）。

        Returns:
            包含 files, symbols, imports, stats 的全局骨架摘要。
        """
        t0 = time.perf_counter()
        files_scanned = 0
        total_lines = 0
        errors: list[str] = []

        for rel_path, full_path in self._walk_files():
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                lines = content.count("\n") + 1
                total_lines += lines
                files_scanned += 1

                ext = full_path.suffix
                if ext in _PY_EXTS:
                    self._regex_scan_python(rel_path, content)
                elif ext in _TS_EXTS:
                    self._regex_scan_ts(rel_path, content)

                # 缓存文件修改时间
                try:
                    self._file_mtimes[rel_path] = full_path.stat().st_mtime
                except OSError:
                    pass

            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel_path}: {exc}")

        self._scan_time = time.perf_counter() - t0

        return {
            "files_scanned": files_scanned,
            "total_lines": total_lines,
            "total_symbols": len(self.symbols),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "scan_time_ms": round(self._scan_time * 1000, 2),
            "errors": errors,
            "symbols_by_kind": self._count_by_kind(),
            "top_files": self._top_files(10),
        }

    def deep_scan(self, files: list[str] | None = None) -> dict[str, Any]:
        """深度 AST 扫描（精确模式，可指定文件子集）。

        对指定文件使用 AST 精确解析，自动降级到正则。
        """
        t0 = time.perf_counter()
        targets = files or [r for r, _ in self._walk_files() if r.endswith(".py")]
        parsed = 0
        fallback = 0

        for rel_path in targets:
            full_path = self.project_dir / rel_path
            if not full_path.exists():
                continue
            content = full_path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(content, filename=rel_path)
                visitor = _SymbolVisitor(rel_path)
                visitor.visit(tree)

                # 注册符号
                for sym in visitor.symbols:
                    self.symbols[sym.fqn] = sym
                    if sym.fqn not in self.file_symbols[rel_path]:
                        self.file_symbols[rel_path].append(sym.fqn)

                # 注册调用边
                for callee, line in visitor.calls:
                    target_fqn = self._resolve_callee(rel_path, callee)
                    if target_fqn:
                        scope_fqn = self._guess_scope_at(rel_path, line)
                        edge = EdgeRef(
                            source=scope_fqn, target=target_fqn,
                            kind="call", file=rel_path, line=line,
                        )
                        self.edges[scope_fqn].append(edge)
                        self.reverse_edges[target_fqn].append(edge)

                # 注册 import 边
                for mod, name, line in visitor.imports:
                    self.file_imports[rel_path].add(mod or name)

                parsed += 1
            except SyntaxError:
                self._regex_scan_python(rel_path, content)
                fallback += 1

        elapsed = time.perf_counter() - t0
        return {
            "parsed_ast": parsed,
            "fallback_regex": fallback,
            "total_symbols": len(self.symbols),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "scan_time_ms": round(elapsed * 1000, 2),
        }

    def storm_center(
        self,
        intent: str,
        keywords: list[str] | None = None,
        top_n: int = 10,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """风暴中心定位 — 多维评分找到项目中与意图最相关的核心节点。

        四维评分:
          1. keyword_score  — 意图关键词与符号名/文件名的匹配度
          2. centrality_score — 引用中心度（归一化入度 + 出度）
          3. complexity_score — 代码体积（行数归一化）
          4. recency_score — 文件修改时间近度

        Args:
            intent: 自然语言意图描述（如 "修复限流中间件"）。
            keywords: 额外关键词列表。
            top_n: 返回前 N 个节点。
            weights: 四维权重覆盖，默认 {keyword: 0.4, centrality: 0.3, complexity: 0.15, recency: 0.15}。

        Returns:
            排名列表 + 聚焦文件推荐。
        """
        w = {
            "keyword": 0.40,
            "centrality": 0.30,
            "complexity": 0.15,
            "recency": 0.15,
        }
        if weights:
            w.update(weights)

        # 构造搜索词集
        search_terms = set(self._tokenize(intent))
        if keywords:
            for kw in keywords:
                search_terms.update(self._tokenize(kw))
        search_terms_lower = {t.lower() for t in search_terms if len(t) > 1}

        if not self.symbols:
            return {"error": "no symbols indexed — run skeleton_scan() or deep_scan() first"}

        # ── 计算各维度原始分 ──
        max_centrality = 1
        max_lines = 1
        now = time.time()
        max_age = 365 * 86400  # 1 year cap

        scores: list[StormScore] = []
        for fqn, sym in self.symbols.items():
            s = StormScore(fqn=fqn)

            # 1) keyword hit
            name_tokens = {t.lower() for t in self._tokenize(sym.name)}
            file_tokens = {t.lower() for t in self._tokenize(sym.file)}
            all_tokens = name_tokens | file_tokens
            if search_terms_lower:
                hits = len(search_terms_lower & all_tokens)
                s.keyword_score = hits / len(search_terms_lower)

            # 2) centrality (in + out degree)
            in_deg = len(self.reverse_edges.get(fqn, []))
            out_deg = len(self.edges.get(fqn, []))
            raw_cent = in_deg + out_deg
            if raw_cent > max_centrality:
                max_centrality = raw_cent

            # 3) complexity (line count)
            raw_lines = max(sym.end_line - sym.line, 1)
            if raw_lines > max_lines:
                max_lines = raw_lines

            # 4) recency
            mtime = self._file_mtimes.get(sym.file, 0)
            age = now - mtime if mtime else max_age
            s.recency_score = max(0, 1 - age / max_age)

            # 暂存原始值
            s.centrality_score = raw_cent  # type: ignore[assignment]
            s.complexity_score = raw_lines  # type: ignore[assignment]
            scores.append(s)

        # ── 归一化 + 加权 ──
        for s in scores:
            s.centrality_score = s.centrality_score / max_centrality  # type: ignore[assignment]
            s.complexity_score = s.complexity_score / max_lines  # type: ignore[assignment]
            s.total = (
                w["keyword"] * s.keyword_score
                + w["centrality"] * s.centrality_score
                + w["complexity"] * s.complexity_score
                + w["recency"] * s.recency_score
            )

        scores.sort(key=lambda x: x.total, reverse=True)
        top = scores[:top_n]

        # 聚焦文件推荐
        focus_files: dict[str, float] = defaultdict(float)
        for s in top:
            sym = self.symbols[s.fqn]
            focus_files[sym.file] += s.total
        sorted_files = sorted(focus_files.items(), key=lambda x: x[1], reverse=True)

        return {
            "intent": intent,
            "keywords": list(search_terms_lower),
            "top_nodes": [s.to_dict() for s in top],
            "focus_files": [{"file": f, "weight": round(w, 4)} for f, w in sorted_files[:5]],
        }

    def decompose(
        self,
        intent: str,
        entry_fqns: list[str] | None = None,
        max_depth: int = 4,
    ) -> dict[str, Any]:
        """DAG 依赖推理 — 从入口节点 BFS 展开依赖树。

        自动检测循环，生成层级任务 ID (1 → 1.1 → 1.1.1)。

        Args:
            intent: 任务意图。
            entry_fqns: 入口 FQN 列表。若不指定，使用 storm_center 自动定位。
            max_depth: 最大展开深度。

        Returns:
            层级依赖树 + 循环警告。
        """
        if not entry_fqns:
            center = self.storm_center(intent, top_n=3)
            entry_fqns = [n["fqn"] for n in center.get("top_nodes", [])[:3]]

        if not entry_fqns:
            return {"error": "no entry points found"}

        tree: list[dict[str, Any]] = []
        visited: set[str] = set()
        cycles: list[str] = []

        def _bfs_layer(fqns: list[str], depth: int, prefix: str) -> list[dict[str, Any]]:
            layer = []
            for i, fqn in enumerate(fqns, 1):
                task_id = f"{prefix}{i}" if prefix else str(i)
                node: dict[str, Any] = {
                    "task_id": task_id,
                    "fqn": fqn,
                    "depth": depth,
                    "symbol": self.symbols[fqn].to_dict() if fqn in self.symbols else None,
                }

                if fqn in visited:
                    cycles.append(f"cycle at {fqn} (task {task_id})")
                    node["cycle"] = True
                    layer.append(node)
                    continue

                visited.add(fqn)

                if depth < max_depth:
                    children_fqns = list(dict.fromkeys(
                        e.target for e in self.edges.get(fqn, [])
                        if e.target in self.symbols
                    ))
                    if children_fqns:
                        node["children"] = _bfs_layer(
                            children_fqns, depth + 1, f"{task_id}.",
                        )
                layer.append(node)
            return layer

        tree = _bfs_layer(entry_fqns, 0, "")

        return {
            "intent": intent,
            "entry_points": entry_fqns,
            "max_depth": max_depth,
            "tree": tree,
            "cycles": cycles,
            "total_nodes": len(visited),
        }

    def impact_analysis(self, fqn: str) -> dict[str, Any]:
        """影响分析 — 找出修改某符号会影响到的所有上游调用者。"""
        if fqn not in self.symbols:
            return {"error": f"symbol not found: {fqn}"}

        affected: dict[str, int] = {}  # fqn → depth
        queue = [(fqn, 0)]
        visited = {fqn}

        while queue:
            current, depth = queue.pop(0)
            for edge in self.reverse_edges.get(current, []):
                if edge.source not in visited:
                    visited.add(edge.source)
                    affected[edge.source] = depth + 1
                    queue.append((edge.source, depth + 1))

        sym = self.symbols[fqn]
        return {
            "target": fqn,
            "target_symbol": sym.to_dict(),
            "affected_count": len(affected),
            "affected": [
                {
                    "fqn": f,
                    "depth": d,
                    "symbol": self.symbols[f].to_dict() if f in self.symbols else None,
                }
                for f, d in sorted(affected.items(), key=lambda x: x[1])
            ],
        }

    def file_overview(self, rel_path: str) -> dict[str, Any]:
        """单文件骨架概览。"""
        syms = self.file_symbols.get(rel_path, [])
        imports = list(self.file_imports.get(rel_path, set()))
        symbols_data = [
            self.symbols[fqn].to_dict()
            for fqn in syms
            if fqn in self.symbols
        ]
        return {
            "file": rel_path,
            "symbols": symbols_data,
            "imports": imports,
            "symbol_count": len(symbols_data),
            "import_count": len(imports),
        }

    def get_snippet(self, fqn: str, context_lines: int = 3) -> dict[str, Any]:
        """获取符号源码片段。"""
        if fqn not in self.symbols:
            return {"error": f"symbol not found: {fqn}"}

        sym = self.symbols[fqn]
        full_path = self.project_dir / sym.file
        if not full_path.exists():
            return {"error": f"file not found: {sym.file}"}

        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, sym.line - 1 - context_lines)
        end = min(len(lines), (sym.end_line or sym.line) + context_lines)
        snippet = "\n".join(lines[start:end])

        return {
            "fqn": fqn,
            "file": sym.file,
            "start_line": start + 1,
            "end_line": end,
            "snippet": snippet,
        }

    def stats(self) -> dict[str, Any]:
        """全局统计信息。"""
        return {
            "total_symbols": len(self.symbols),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "total_files": len(self.file_symbols),
            "symbols_by_kind": self._count_by_kind(),
            "top_files": self._top_files(10),
            "top_centrality": self._top_centrality(10),
            "scan_time_ms": round(self._scan_time * 1000, 2),
        }

    # ─── 正则扫描 (容错模式) ───────────────────────────────────────────

    def _regex_scan_python(self, rel_path: str, content: str) -> None:
        """Python 正则骨架扫描 — 对 SyntaxError 完全免疫。"""
        lines = content.splitlines()

        # 1) 提取符号定义
        scope_stack: list[tuple[str, int]] = [("<module>", -1)]
        for m in _PY_DEF_RE.finditer(content):
            indent = len(m.group("indent"))
            kind = m.group("kind")
            name = m.group("name")
            line_no = content[:m.start()].count("\n") + 1

            # 维护作用域栈
            while len(scope_stack) > 1 and scope_stack[-1][1] >= indent:
                scope_stack.pop()
            scope = scope_stack[-1][0]

            # 估算 end_line（下一个同级定义或文件末尾）
            end_line = len(lines)
            rest = content[m.end():]
            for m2 in _PY_DEF_RE.finditer(rest):
                next_indent = len(m2.group("indent"))
                if next_indent <= indent:
                    end_line = line_no + rest[:m2.start()].count("\n")
                    break

            sym = SymbolDef(
                name=name,
                kind="function" if kind == "def" else "class",
                file=rel_path,
                line=line_no,
                end_line=end_line,
                scope=scope,
            )

            # 抓装饰器
            if line_no > 1:
                for back in range(line_no - 2, max(0, line_no - 6), -1):
                    stripped = lines[back].strip() if back < len(lines) else ""
                    dm = _PY_DECORATOR_RE.match(lines[back]) if back < len(lines) else None
                    if dm:
                        sym.decorators.append(dm.group("dec"))
                    elif stripped and not stripped.startswith("#"):
                        break

            self.symbols[sym.fqn] = sym
            if sym.fqn not in self.file_symbols[rel_path]:
                self.file_symbols[rel_path].append(sym.fqn)

            if kind == "class":
                scope_stack.append((name, indent))

        # 2) 提取 import
        for m in _PY_IMPORT_RE.finditer(content):
            from_mod = m.group("from")
            imp_mod = m.group("imp")
            if from_mod:
                self.file_imports[rel_path].add(from_mod)
            elif imp_mod:
                for part in imp_mod.split(","):
                    self.file_imports[rel_path].add(part.strip().split()[0])

        # 3) 提取调用（粗粒度）
        for m in _PY_CALL_RE.finditer(content):
            callee = m.group("callee")
            if callee in ("if", "for", "while", "with", "return", "yield", "print", "range", "len", "str", "int", "float", "list", "dict", "set", "tuple", "type", "super", "isinstance", "issubclass", "hasattr", "getattr", "setattr"):
                continue
            line_no = content[:m.start()].count("\n") + 1
            target_fqn = self._resolve_callee(rel_path, callee)
            if target_fqn:
                source_fqn = self._guess_scope_at(rel_path, line_no)
                edge = EdgeRef(
                    source=source_fqn, target=target_fqn,
                    kind="call", file=rel_path, line=line_no,
                )
                self.edges[source_fqn].append(edge)
                self.reverse_edges[target_fqn].append(edge)

    def _regex_scan_ts(self, rel_path: str, content: str) -> None:
        """TypeScript/JavaScript 正则骨架扫描。"""
        for m in _TS_DEF_RE.finditer(content):
            kind_raw = m.group("kind")
            name = m.group("name")
            line_no = content[:m.start()].count("\n") + 1

            kind_map = {
                "function": "function", "class": "class",
                "interface": "interface", "type": "type",
                "enum": "enum", "const": "variable",
                "let": "variable", "var": "variable",
            }
            sym = SymbolDef(
                name=name,
                kind=kind_map.get(kind_raw, "variable"),
                file=rel_path,
                line=line_no,
            )
            self.symbols[sym.fqn] = sym
            if sym.fqn not in self.file_symbols[rel_path]:
                self.file_symbols[rel_path].append(sym.fqn)

        for m in _TS_IMPORT_RE.finditer(content):
            self.file_imports[rel_path].add(m.group("mod"))

    # ─── 辅助方法 ─────────────────────────────────────────────────────

    def _walk_files(self):
        """遍历项目文件，过滤忽略目录。"""
        for root, dirs, filenames in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
            for fname in filenames:
                full = Path(root) / fname
                if full.suffix in _ALL_EXTS:
                    rel = str(full.relative_to(self.project_dir)).replace("\\", "/")
                    yield rel, full

    def _resolve_callee(self, rel_path: str, callee: str) -> str | None:
        """尝试将调用名解析为已知 FQN。"""
        # 直接匹配: 同文件内的符号
        for fqn, sym in self.symbols.items():
            if sym.name == callee and sym.file == rel_path:
                return fqn
            if sym.name == callee:
                return fqn
        # 点号调用 a.b → 查 b
        if "." in callee:
            parts = callee.split(".")
            for fqn, sym in self.symbols.items():
                if sym.name == parts[-1]:
                    return fqn
        return None

    def _guess_scope_at(self, rel_path: str, line: int) -> str:
        """推测某行所在的最近作用域 FQN。"""
        best: str = f"{rel_path}::<module>"
        best_line = 0
        for fqn, sym in self.symbols.items():
            if sym.file == rel_path and sym.line <= line and sym.line > best_line:
                best = fqn
                best_line = sym.line
        return best

    def _count_by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for sym in self.symbols.values():
            counts[sym.kind] += 1
        return dict(counts)

    def _top_files(self, n: int) -> list[dict[str, Any]]:
        file_counts: dict[str, int] = defaultdict(int)
        for sym in self.symbols.values():
            file_counts[sym.file] += 1
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"file": f, "symbols": c} for f, c in sorted_files[:n]]

    def _top_centrality(self, n: int) -> list[dict[str, Any]]:
        cent: dict[str, int] = {}
        for fqn in self.symbols:
            in_d = len(self.reverse_edges.get(fqn, []))
            out_d = len(self.edges.get(fqn, []))
            cent[fqn] = in_d + out_d
        sorted_c = sorted(cent.items(), key=lambda x: x[1], reverse=True)
        return [{"fqn": f, "degree": d} for f, d in sorted_c[:n] if d > 0]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """将文本拆分为搜索 token（支持 CamelCase + snake_case + 中文分词）。"""
        tokens: list[str] = []
        # CamelCase split
        camel = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        # snake_case split + 其他分隔
        for word in re.split(r"[\s_./\\:,;()\[\]{}\-]+", camel):
            word = word.strip()
            if len(word) > 1:
                tokens.append(word)
        # 中文字符单独提取
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                tokens.append(ch)
        return tokens
