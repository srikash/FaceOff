import re

import pytest

from faceoff.scratch import workspace


def test_workspace_name_and_cleanup(tmp_path):
    with workspace(tmp_path) as ws:
        assert re.fullmatch(r"\.faceoff-\d{8}T\d{6}Z-[0-9a-f]{12}", ws.root.name)
        ws.path("x").write_text("data")
        assert ws.root.is_dir()
    assert not ws.root.exists()


def test_workspace_removed_on_error(tmp_path):
    with pytest.raises(RuntimeError), workspace(tmp_path) as ws:
        raise RuntimeError("boom")
    assert not ws.root.exists()


def test_workspace_is_a_hidden_folder_inside_the_given_parent(tmp_path):
    with workspace(tmp_path) as ws:
        assert ws.root.parent == tmp_path and ws.root.name.startswith(".")
