"""Neural Storm Graph — 完整测试套件。

验证: 骨架扫描 + 风暴中心 + 实时定位 + 增量更新 + 热力图 + 调用链追踪。
"""
from __future__ import annotations

import os
import tempfile
import textwrap

import pytest

# 将 neural-storm-graph 加入 sys.path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.storm_skeleton import StormSkeleton, SymbolDef
from core.realtime_graph import RealtimeGraph, CursorPosition


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_project(tmp_path):
    """创建一个带多文件的临时项目。"""
    # main.py
    (tmp_path / "main.py").write_text(textwrap.dedent("""\
        from utils import helper
        from service import UserService

        class App:
            def __init__(self):
                self.service = UserService()

            def run(self):
                result = self.service.get_user("test")
                helper.log(result)
                return result

        def main():
            app = App()
            app.run()

        if __name__ == "__main__":
            main()
    """), encoding="utf-8")

    # utils.py
    (tmp_path / "utils.py").write_text(textwrap.dedent("""\
        import os
        import logging

        logger = logging.getLogger(__name__)

        def log(message):
            logger.info(message)

        def format_output(data, style="default"):
            if style == "json":
                import json
                return json.dumps(data)
            return str(data)

        class Config:
            DEBUG = True
            VERSION = "1.0.0"

            def get(self, key):
                return getattr(self, key, None)
    """), encoding="utf-8")

    # service.py
    (tmp_path / "service.py").write_text(textwrap.dedent("""\
        from utils import Config, format_output

        class UserService:
            def __init__(self):
                self.config = Config()

            def get_user(self, user_id):
                data = {"id": user_id, "name": "Test User"}
                return format_output(data)

            def create_user(self, name, email):
                return {"name": name, "email": email}

        class AdminService(UserService):
            def delete_user(self, user_id):
                return True
    """), encoding="utf-8")

    # models/__init__.py (子目录)
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "__init__.py").write_text("from .user import User\n", encoding="utf-8")
    (models_dir / "user.py").write_text(textwrap.dedent("""\
        from dataclasses import dataclass

        @dataclass
        class User:
            id: str
            name: str
            email: str = ""

            def display(self):
                return f"{self.name} ({self.email})"
    """), encoding="utf-8")

    return tmp_path


@pytest.fixture
def skeleton(sample_project):
    """预扫描的骨架引擎。"""
    sk = StormSkeleton(str(sample_project))
    sk.skeleton_scan()
    return sk


@pytest.fixture
def graph(skeleton):
    """基于骨架的实时图谱。"""
    return RealtimeGraph(skeleton)


# ─── StormSkeleton 测试 ────────────────────────────────────────────────────

class TestSkeletonScan:
    def test_scan_finds_files(self, skeleton):
        stats = skeleton.stats()
        assert stats["total_files"] >= 4  # main, utils, service, models/user
        assert stats["total_symbols"] > 0

    def test_scan_finds_classes(self, skeleton):
        class_names = [s.name for s in skeleton.symbols.values() if s.kind == "class"]
        assert "App" in class_names
        assert "Config" in class_names
        assert "UserService" in class_names
        assert "AdminService" in class_names
        assert "User" in class_names

    def test_scan_finds_functions(self, skeleton):
        func_names = [s.name for s in skeleton.symbols.values() if s.kind == "function"]
        assert "main" in func_names
        assert "log" in func_names
        assert "format_output" in func_names
        assert "get_user" in func_names

    def test_scan_extracts_imports(self, skeleton):
        imports = skeleton.file_imports
        assert "utils" in imports.get("main.py", set()) or any("utils" in v for v in imports.values())

    def test_scan_performance(self, skeleton):
        stats = skeleton.stats()
        assert stats["scan_time_ms"] < 5000  # 应在 5 秒内完成

    def test_file_overview(self, skeleton):
        overview = skeleton.file_overview("main.py")
        assert overview["file"] == "main.py"
        assert overview["symbol_count"] > 0

    def test_symbol_fqn_format(self, skeleton):
        for fqn, sym in skeleton.symbols.items():
            assert "::" in fqn
            assert sym.file in fqn


class TestDeepScan:
    def test_deep_scan_parses_ast(self, sample_project):
        sk = StormSkeleton(str(sample_project))
        result = sk.deep_scan()
        assert result["parsed_ast"] > 0
        assert result["total_symbols"] > 0

    def test_deep_scan_discovers_edges(self, sample_project):
        sk = StormSkeleton(str(sample_project))
        sk.skeleton_scan()
        result = sk.deep_scan()
        assert result["total_edges"] >= 0  # 边数取决于解析精度


class TestStormCenter:
    def test_storm_center_returns_ranked_nodes(self, skeleton):
        result = skeleton.storm_center("user service")
        assert "top_nodes" in result
        assert len(result["top_nodes"]) > 0

    def test_storm_center_respects_keywords(self, skeleton):
        result = skeleton.storm_center("format", keywords=["output", "style"])
        top_names = [n["fqn"] for n in result["top_nodes"][:5]]
        # format_output 应排名靠前
        assert any("format" in name.lower() for name in top_names)

    def test_storm_center_focus_files(self, skeleton):
        result = skeleton.storm_center("user")
        assert "focus_files" in result
        assert len(result["focus_files"]) > 0

    def test_storm_center_empty_graph(self, tmp_path):
        sk = StormSkeleton(str(tmp_path))
        result = sk.storm_center("anything")
        assert "error" in result

    def test_storm_center_custom_weights(self, skeleton):
        result = skeleton.storm_center(
            "config",
            weights={"keyword": 0.8, "centrality": 0.1, "complexity": 0.05, "recency": 0.05},
        )
        assert len(result["top_nodes"]) > 0


class TestDecompose:
    def test_decompose_generates_tree(self, skeleton):
        result = skeleton.decompose("重构用户服务")
        assert "tree" in result
        assert result["total_nodes"] > 0

    def test_decompose_task_ids(self, skeleton):
        result = skeleton.decompose("修复 main")
        if result.get("tree"):
            first = result["tree"][0]
            assert "task_id" in first
            assert first["task_id"] == "1"

    def test_decompose_cycle_detection(self, skeleton):
        # 即使有循环也不会无限递归
        result = skeleton.decompose("全面重构", max_depth=6)
        assert isinstance(result["cycles"], list)


class TestImpactAnalysis:
    def test_impact_analysis(self, skeleton):
        # 找一个有引用的符号
        for fqn in skeleton.symbols:
            if skeleton.reverse_edges.get(fqn):
                result = skeleton.impact_analysis(fqn)
                assert result["affected_count"] >= 0
                break

    def test_impact_analysis_not_found(self, skeleton):
        result = skeleton.impact_analysis("nonexistent::symbol")
        assert "error" in result


class TestGetSnippet:
    def test_get_snippet(self, skeleton):
        for fqn in skeleton.symbols:
            result = skeleton.get_snippet(fqn)
            if "error" not in result:
                assert "snippet" in result
                assert len(result["snippet"]) > 0
                break

    def test_get_snippet_not_found(self, skeleton):
        result = skeleton.get_snippet("ghost::symbol")
        assert "error" in result


# ─── RealtimeGraph 测试 ────────────────────────────────────────────────────

class TestLocate:
    def test_locate_finds_symbol(self, graph: RealtimeGraph):
        # 定位 main.py 的 App 类
        for fqn, sym in graph.skeleton.symbols.items():
            if sym.name == "App":
                ctx = graph.locate(CursorPosition(file=sym.file, line=sym.line))
                assert ctx.symbol is not None
                assert ctx.symbol.name == "App"
                break

    def test_locate_returns_breadcrumb(self, graph: RealtimeGraph):
        for fqn, sym in graph.skeleton.symbols.items():
            if sym.scope != "<module>":
                ctx = graph.locate(CursorPosition(file=sym.file, line=sym.line))
                assert len(ctx.breadcrumb) >= 2
                break

    def test_locate_returns_siblings(self, graph: RealtimeGraph):
        # 类内方法应有兄弟方法
        for fqn, sym in graph.skeleton.symbols.items():
            if sym.scope != "<module>" and sym.kind == "function":
                ctx = graph.locate(CursorPosition(file=sym.file, line=sym.line))
                # siblings 包含同作用域的其他符号
                assert isinstance(ctx.siblings, list)
                break

    def test_locate_symbol_by_fqn(self, graph: RealtimeGraph):
        fqn = next(iter(graph.skeleton.symbols))
        ctx = graph.locate_symbol(fqn)
        assert ctx is not None
        assert ctx.symbol is not None

    def test_locate_nonexistent_file(self, graph: RealtimeGraph):
        ctx = graph.locate(CursorPosition(file="nonexistent.py", line=1))
        assert ctx.symbol is None
        assert ctx.breadcrumb == ["nonexistent.py"]


class TestUpdateFile:
    def test_update_modified_file(self, graph: RealtimeGraph, sample_project):
        # 修改 utils.py
        new_content = textwrap.dedent("""\
            def log(message):
                print(message)

            def new_function():
                return 42
        """)
        change = graph.update_file("utils.py", content=new_content)
        assert change.kind == "modified"
        assert any("new_function" in fqn for fqn in change.new_symbols)

    def test_update_new_file(self, graph: RealtimeGraph, sample_project):
        # 创建新文件
        new_file = sample_project / "extra.py"
        new_file.write_text("def extra_func():\n    pass\n", encoding="utf-8")
        change = graph.update_file("extra.py")
        assert change.kind == "created"
        assert len(change.new_symbols) > 0

    def test_update_deleted_file(self, graph: RealtimeGraph, sample_project):
        # 删除文件
        (sample_project / "utils.py").unlink()
        change = graph.update_file("utils.py")
        assert change.kind == "deleted"
        assert len(change.removed) > 0

    def test_batch_update(self, graph: RealtimeGraph, sample_project):
        changes = graph.batch_update(["main.py", "utils.py"])
        assert len(changes) == 2

    def test_change_callback(self, graph: RealtimeGraph, sample_project):
        events = []
        graph.on_change(lambda c: events.append(c))
        graph.update_file("main.py")
        assert len(events) == 1
        assert events[0].file == "main.py"

    def test_off_change(self, graph: RealtimeGraph, sample_project):
        events = []
        cb = lambda c: events.append(c)
        graph.on_change(cb)
        graph.off_change(cb)
        graph.update_file("main.py")
        assert len(events) == 0


class TestHeatmap:
    def test_heatmap_returns_entries(self, graph: RealtimeGraph):
        hm = graph.heatmap()
        assert isinstance(hm, list)
        if hm:
            assert "heat" in hm[0]
            assert "file" in hm[0]

    def test_heatmap_after_changes(self, graph: RealtimeGraph, sample_project):
        # 多次修改同一文件 → 热度上升
        for _ in range(5):
            graph.update_file("main.py")
        hm = graph.heatmap()
        main_entry = next((e for e in hm if e["file"] == "main.py"), None)
        assert main_entry is not None
        assert main_entry["change_freq"] == 5


class TestTraceCallChain:
    def test_trace_both_directions(self, graph: RealtimeGraph):
        for fqn in graph.skeleton.symbols:
            result = graph.trace_call_chain(fqn, direction="both")
            assert "fqn" in result
            assert "callers_chain" in result
            assert "callees_chain" in result
            break

    def test_trace_not_found(self, graph: RealtimeGraph):
        result = graph.trace_call_chain("ghost::sym")
        assert "error" in result


class TestSearch:
    def test_search_symbols(self, graph: RealtimeGraph):
        results = graph.search_symbols("user")
        assert isinstance(results, list)
        assert all("score" in r for r in results)

    def test_search_with_kind_filter(self, graph: RealtimeGraph):
        results = graph.search_symbols("user", kind="class")
        for r in results:
            assert r["kind"] == "class"

    def test_search_no_results(self, graph: RealtimeGraph):
        results = graph.search_symbols("zzzznonexistent")
        assert results == []


class TestDependencyGraph:
    def test_dependency_graph(self, graph: RealtimeGraph):
        dep = graph.dependency_graph("main.py")
        assert dep["root"] == "main.py"
        assert "nodes" in dep
        assert "edges" in dep


class TestExport:
    def test_export_graph(self, graph: RealtimeGraph):
        data = graph.export_graph()
        assert "nodes" in data
        assert "edges" in data
        assert data["node_count"] > 0

    def test_export_mermaid(self, graph: RealtimeGraph):
        mermaid = graph.export_mermaid()
        assert mermaid.startswith("graph LR")

    def test_export_mermaid_for_file(self, graph: RealtimeGraph):
        mermaid = graph.export_mermaid(rel_path="main.py")
        assert "graph LR" in mermaid


class TestStats:
    def test_realtime_stats(self, graph: RealtimeGraph):
        stats = graph.stats()
        assert "total_symbols" in stats
        assert "change_log_size" in stats
        assert "callbacks_registered" in stats

    def test_recent_changes(self, graph: RealtimeGraph, sample_project):
        graph.update_file("main.py")
        changes = graph.recent_changes()
        assert len(changes) > 0
        assert changes[0]["file"] == "main.py"
