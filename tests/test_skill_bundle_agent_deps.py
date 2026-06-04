"""Skill bundle ↔ AgentDefinition 分层：推导与注册校验。"""
from __future__ import annotations

import pytest

from agent_platform.agents.stock_recap.manifest import _build_definition
from agent_platform.agents.stock_recap.skills import bundle_root
from agent_platform.core.errors import AgentDependencyError
from agent_platform.core.registry import AgentDefinition, AgentRegistry, AgentCapability
from agent_platform.domain.models import GenerateRequest, GenerateResponse
from agent_platform.runtime.agent_validation import validate_agent_dependencies
from agent_platform.skills.bundle import (
    enrich_bundle_manifest,
    read_bundle_manifest,
    resolve_skill_id_from_path,
    with_skill_bundle,
)


def test_with_skill_bundle_derives_ids_from_manifest():
    manifest = read_bundle_manifest(bundle_root())
    defn = with_skill_bundle(
        AgentDefinition(
            id="stock-recap",
            display_name="x",
            description="x",
            request_model=GenerateRequest,
            response_model=GenerateResponse,
            capabilities=[AgentCapability.REPORT],
            runner=lambda **kwargs: None,
        ),
        bundle_key="stock-recap",
        bundle_root=bundle_root(),
    )
    assert defn.skill_bundle == "stock-recap"
    assert defn.skills == list(manifest.skill_ids)
    assert defn.skill_mode_map == manifest.mode_to_skill_id
    assert "a_share.daily_recap" in defn.skills
    assert defn.skill_mode_map["daily"] == "a_share.daily_recap"


def test_build_definition_matches_bundle():
    defn = _build_definition()
    manifest = read_bundle_manifest(bundle_root())
    assert defn.skills == list(manifest.skill_ids)
    assert defn.skill_mode_map == manifest.mode_to_skill_id


def test_resolve_skill_id_from_skill_md():
    rel = "a_share_daily_recap/SKILL.md"
    assert resolve_skill_id_from_path(bundle_root(), rel) == "a_share.daily_recap"


def test_manifest_must_not_include_id_field(tmp_path):
    bundle = tmp_path / "bad"
    (bundle / "skill_a").mkdir(parents=True)
    (bundle / "skill_a" / "SKILL.md").write_text(
        "---\nname: skill.a\n---\nbody",
        encoding="utf-8",
    )
    manifest = {
        "bundle_version": "0",
        "skills": [{"id": "skill.a", "path": "skill_a/SKILL.md"}],
        "mode_to_skill_id": {},
    }
    with pytest.raises(ValueError, match="must not include 'id'"):
        enrich_bundle_manifest(bundle, manifest)


def test_enrich_rejects_missing_frontmatter_name(tmp_path):
    bundle = tmp_path / "bad"
    (bundle / "skill_a").mkdir(parents=True)
    (bundle / "skill_a" / "SKILL.md").write_text("no frontmatter", encoding="utf-8")
    manifest = {"bundle_version": "0", "skills": [{"path": "skill_a/SKILL.md"}]}
    with pytest.raises(ValueError, match="must define 'name'"):
        enrich_bundle_manifest(bundle, manifest)


def test_validate_rejects_skill_list_drift_from_bundle():
    defn = _build_definition()
    bad = AgentDefinition(
        id=defn.id,
        display_name=defn.display_name,
        description=defn.description,
        request_model=defn.request_model,
        response_model=defn.response_model,
        capabilities=defn.capabilities,
        runner=defn.runner,
        skill_bundle=defn.skill_bundle,
        skills=["a_share.daily_recap"],
        skill_mode_map={"daily": "a_share.daily_recap"},
        mcp_tool_names=defn.mcp_tool_names,
    )
    with pytest.raises(AgentDependencyError, match="diverge from bundle"):
        validate_agent_dependencies(bad)


def test_registry_validates_when_validator_set():
    reg = AgentRegistry()
    reg.set_dependency_validator(validate_agent_dependencies)
    reg.register(_build_definition())


def test_registry_skips_validation_without_validator():
    reg = AgentRegistry()
    bad = _build_definition()
    bad = AgentDefinition(
        id=bad.id,
        display_name=bad.display_name,
        description=bad.description,
        request_model=bad.request_model,
        response_model=bad.response_model,
        capabilities=bad.capabilities,
        runner=bad.runner,
        skill_bundle=bad.skill_bundle,
        skills=["totally.fake.skill"],
        skill_mode_map={},
        mcp_tool_names=bad.mcp_tool_names,
    )
    reg.register(bad)
