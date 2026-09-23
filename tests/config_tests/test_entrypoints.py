"""Configuration selection must not require editing shared package defaults."""

import importlib
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module,class_name",
    [
        ("curb_segmenter", "CurbSegmenterConfig"),
        ("sign_reader", "SignReaderConfig"),
        ("policy_applier", "PolicyApplierConfig"),
        ("api_updater", "ApiUpdaterConfig"),
        ("blockface_creator", "BlockfaceCreatorConfig"),
    ],
)
@pytest.mark.parametrize("custom", [False, True])
def test_config_path_selection(monkeypatch, module, class_name, custom) -> None:
    entry = importlib.import_module(f"{module}.__main__")
    selected, runs = [], []
    monkeypatch.setattr(
        entry, "load_from_yaml", lambda path: selected.append(path) or {}
    )
    monkeypatch.setattr(entry, class_name, lambda **kwargs: "validated")
    monkeypatch.setattr(entry, module, lambda config: runs.append(config))
    monkeypatch.setattr(entry, "set_log_context", lambda context: None)
    entry.main(["--config", "configs/chinatown/example.yaml"] if custom else [])
    expected = (
        Path("configs/chinatown/example.yaml")
        if custom
        else Path(entry.__file__).resolve().parent / "config.yaml"
    )
    assert selected == [expected]
    assert runs == ["validated"]
