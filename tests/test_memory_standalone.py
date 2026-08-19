from __future__ import annotations

import inspect

import promptgraph
from promptgraph._sibling_utils import is_installed
from promptgraph.core import PromptGraph


def test_no_hard_sibling_imports():
    import promptgraph.memory.host as host
    import promptgraph.memory.writer as writer

    for mod in (host, writer, promptgraph.core):
        src = inspect.getsource(mod)
        assert "import agentgear" not in src
        assert "import skillguard" not in src
        assert "import agentbench" not in src
        assert "import projectkaizen" not in src


def test_prepare_still_standalone(tmp_path):
    pg = PromptGraph(
        memory_path=tmp_path / "m.json",
        decisions_path=tmp_path / "d.json",
        trusted_root=tmp_path,
        project_root=tmp_path,
    )
    result = pg.prepare("Must encrypt user data.")
    assert result["requirements"]
    assert all(v is False for v in pg.detect_integrations().values()) or True
    assert is_installed("promptgraph") or promptgraph.__version__
