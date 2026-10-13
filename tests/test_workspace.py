import re

import pytest

from faceoff.workspace import workspace


def test_workspace_name_and_cleanup(tmp_path):
    with workspace(tmp_path) as ws:
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d_[0-9a-f]{12}", ws.root.name)
        ws.path("x").write_text("data")
        assert ws.root.is_dir()
    assert not ws.root.exists()


def test_workspace_removed_on_error(tmp_path):
    with pytest.raises(RuntimeError):
        with workspace(tmp_path) as ws:
            raise RuntimeError("boom")
    assert not ws.root.exists()
