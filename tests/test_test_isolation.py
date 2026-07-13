import os
from pathlib import Path

import pytest

from helpers import fake_pat


def test_unit_tests_use_a_disposable_home(tmp_path):
    home = Path(os.environ["HOME"])

    assert home == tmp_path / "home"
    assert Path(os.environ["XDG_CONFIG_HOME"]) == home / ".config"
    assert Path(os.environ["APPDATA"]) == home / "AppData" / "Roaming"


@pytest.mark.parametrize("credential", [fake_pat("pytest-node-id")])
def test_credential_shaped_parameters_are_not_exposed_in_node_ids(
    request, credential
):
    assert credential not in request.node.nodeid
