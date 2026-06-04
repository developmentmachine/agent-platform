import json

import pytest

import agent_platform.config.settings as settings_module
from agent_platform.agents.stock_recap.manifest import _build_definition
from agent_platform.runtime.scope import agent_execution
from agent_platform.skills.loader import (
    clear_skill_manifest_cache,
    list_registered_skills,
    load_skill_document,
    load_skill_overlay_for_mode,
    resolve_skill_id_for_mode,
    skill_bundle_version,
)


@pytest.fixture(autouse=True)
def _reset_skill_cache(monkeypatch: pytest.MonkeyPatch):
    clear_skill_manifest_cache()
    yield
    monkeypatch.delenv("RECAP_SKILL_EXTRA_DIRS", raising=False)
    settings_module._settings_instance = None
    clear_skill_manifest_cache()


def test_manifest_version():
    assert skill_bundle_version() == "1.0.0"


def test_resolve_daily_global_manifest():
    """全局合并 manifest 的 mode 表（目录/合并测试用，非 Agent overlay）。"""
    assert resolve_skill_id_for_mode("daily") == "a_share.daily_recap"


def test_overlay_daily_contains_skill_body():
    with agent_execution(_build_definition()):
        doc = load_skill_overlay_for_mode("daily")
        assert doc is not None
        assert "RecapDaily" in doc.body or "daily" in doc.body.lower()


def test_override_unknown_raises_if_not_in_agent_allowlist():
    with agent_execution(_build_definition()):
        with pytest.raises(ValueError, match="not in agent skill allowlist"):
            load_skill_overlay_for_mode("daily", override_skill_id="does.not.exist")


def test_extra_skill_dir_merges_into_global_catalog(monkeypatch, tmp_path):
    bundle = tmp_path / "ext"
    (bundle / "plugin_daily").mkdir(parents=True)
    (bundle / "plugin_daily" / "SKILL.md").write_text(
        "---\nname: plugin.daily\n---\nPlugin body unique xyz",
        encoding="utf-8",
    )
    manifest = {
        "bundle_version": "0.0.0",
        "mode_to_skill_id": {"daily": "plugin.daily"},
        "skills": [{"path": "plugin_daily/SKILL.md", "description": "from extra dir"}],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    settings_module._settings_instance = None
    monkeypatch.setenv("RECAP_SKILL_EXTRA_DIRS", str(bundle))
    clear_skill_manifest_cache()

    doc = load_skill_document("plugin.daily")
    assert doc is not None
    assert "xyz" in doc.body
    ids = {s["id"] for s in list_registered_skills()}
    assert "plugin.daily" in ids
    assert "a_share.daily_recap" in ids


def test_extra_skill_dir_does_not_override_stock_recap_agent_overlay(monkeypatch, tmp_path):
    """全局 mode 可被 extra dir 覆盖；stock-recap AgentScope 仍用自身 skill_mode_map。"""
    bundle = tmp_path / "ext"
    (bundle / "plugin_daily").mkdir(parents=True)
    (bundle / "plugin_daily" / "SKILL.md").write_text(
        "---\nname: plugin.daily\n---\nbody",
        encoding="utf-8",
    )
    manifest = {
        "bundle_version": "0.0.0",
        "mode_to_skill_id": {"daily": "plugin.daily"},
        "skills": [{"path": "plugin_daily/SKILL.md"}],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("RECAP_SKILL_EXTRA_DIRS", str(bundle))
    clear_skill_manifest_cache()

    assert resolve_skill_id_for_mode("daily") == "plugin.daily"

    with agent_execution(_build_definition()):
        doc = load_skill_overlay_for_mode("daily")
        assert doc is not None
        assert doc.skill_id == "a_share.daily_recap"


def test_entry_point_skill_bundle(monkeypatch):
    import agent_platform.skills.loader as loader_mod

    class _Eps:
        @staticmethod
        def select(*, group: str):
            from importlib.metadata import EntryPoint

            if group != "agent_platform.skills":
                return ()
            return (
                EntryPoint(
                    name="fixture_ep",
                    value="tests.fixtures.ep_roots:ROOT",
                    group="agent_platform.skills",
                ),
            )

    monkeypatch.setattr(loader_mod.metadata, "entry_points", lambda: _Eps())
    clear_skill_manifest_cache()

    assert resolve_skill_id_for_mode("strategy") == "ep.strategy_skill"
    doc = load_skill_document("ep.strategy_skill")
    assert doc is not None
    assert "entry point" in doc.body.lower()
