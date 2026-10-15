"""Offline catalog/preview contracts, using only synthetic config and cookie users."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

import pytest
from flask import Flask, g, request
from flask_login import LoginManager, UserMixin

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard/backend"))
from execution_catalog import legacy_to_catalog, validate_references
from execution_routing import select_route
from execution_operations import execution_templates

FIXTURE = {
    "active_provider": "omnirouter",
    "providers": {
        "omnirouter": {"cli_command": "opencode", "model_chain": ["Britto-Drael", "Britto-Review"],
                       "fallback_providers": ["codex_auth", "anthropic"],
                       "default_base_url": "https://user:PRIVATE_PASSWORD@private.invalid/v1?key=PRIVATE_KEY",
                       "env_vars": {"OPENAI_API_KEY": "PRIVATE_KEY"}},
        "codex_auth": {"cli_command": "openclaude", "default_model": "legacy-codex-alias"},
        "anthropic": {"cli_command": "claude"},
    },
}
ROUTING = {"enabled": True, "default_combo": "REVIEW",
           "combos": {"REVIEW": ["anthropic", "missing", "omnirouter"]},
           "roles": {"oath": "REVIEW"}}


def test_projection_preserves_full_chain_alias_order_and_inputs_without_secret_values():
    config = copy.deepcopy(FIXTURE); original = copy.deepcopy(config)
    catalog = legacy_to_catalog(config, ROUTING)
    assert config == original and validate_references(catalog)
    assert [(r.provider_id, r.model_id) for r in catalog.pools[0].routes] == [
        ("omnirouter", "omnirouter:Britto-Drael"), ("omnirouter", "omnirouter:Britto-Review"),
        ("codex_auth", "codex_auth:legacy-codex-alias"), ("anthropic", "anthropic:_legacy_default")]
    assert [r.provider_id for r in catalog.pools[1].routes] == ["anthropic", "omnirouter", "omnirouter", "codex_auth"]
    output = json.dumps(catalog.payload())
    assert all(v not in output for v in ["PRIVATE_KEY", "PRIVATE_PASSWORD", "private.invalid"])
    assert next(p for p in catalog.providers if p.id == "codex_auth").harness_id == "openclaude"
    assert all(h.state == "coming_soon" and h.adapter_id is None for h in catalog.harnesses if h.id in {"codex", "hermes"})


@pytest.mark.parametrize("active", ["none", "absent", None])
def test_kill_switch_and_unknown_active_never_default_to_a_live_chain(active):
    config = copy.deepcopy(FIXTURE);config["active_provider"] = active
    catalog = legacy_to_catalog(config, ROUTING)
    assert all(not p.routes for p in catalog.pools)
    decision = select_route(catalog, "summarize_ticket")
    assert decision["selected"] is None and not decision["execution_allowed"]
    assert ("active_provider_disabled" if active == "none" else "no_configured_route") in decision["reasons"]


def test_revision_tracks_nonsecret_route_and_order_not_auth_values():
    a = legacy_to_catalog(FIXTURE, ROUTING).payload()
    config = copy.deepcopy(FIXTURE);config["providers"]["omnirouter"]["env_vars"]["OPENAI_API_KEY"] = "ROTATED_PRIVATE"
    assert legacy_to_catalog(config, ROUTING).payload()["catalog_revision"] == a["catalog_revision"]
    config["providers"]["omnirouter"]["model_chain"].reverse()
    assert legacy_to_catalog(config, ROUTING).payload()["catalog_revision"] != a["catalog_revision"]


def test_template_adaptation_keeps_role_mapping_without_enabling_work():
    catalog = legacy_to_catalog(FIXTURE, ROUTING)
    templates = execution_templates(catalog)
    assert templates["roles"] == {"oath": "combo:REVIEW"}
    assert templates["default_pool"] == "combo:REVIEW"
    assert all(t["execution_enabled"] is False for t in templates["templates"])


def test_preview_is_deterministic_prefers_config_order_but_never_authorizes():
    catalog = legacy_to_catalog(FIXTURE, ROUTING)
    a = select_route(catalog, "summarize_ticket")
    assert a == select_route(catalog, "summarize_ticket")
    assert a["preferred"]["model_id"] == "omnirouter:Britto-Drael"
    assert a["selected"] is None and a["attempts"] == [] and a["provider_calls"] == 0
    assert a["scope"] == "configuration_only"
    reasons = a["preferred"]["reasons"]
    assert all(r in reasons for r in ["runtime_version_unknown", "credential_resolution_not_performed",
                                     "budget_unknown", "capability_unverified:no_tools", "model_capabilities_unknown"])


def test_independent_entity_filters_never_cross_provider_model_references():
    catalog = legacy_to_catalog(FIXTURE)
    result = select_route(catalog, "draft_ticket", selection={"harness_id": "opencode", "provider_id": "omnirouter", "model_id": "omnirouter:Britto-Review"})
    assert result["preferred"]["ordinal"] == 2
    wrong = select_route(catalog, "draft_ticket", selection={"provider_id": "anthropic", "model_id": "omnirouter:Britto-Review"})
    assert wrong["preferred"] is None and "selection_not_in_pool" in wrong["reasons"]


def test_repository_proof_does_not_claim_installed_or_live_capability():
    catalog = legacy_to_catalog(FIXTURE)
    h = catalog.harnesses[0]
    assert h.proof_version == "1.17.18" and h.runtime_version is None and h.runtime_capabilities == ()
    wrong = replace(h, runtime_version="1.18.18")
    changed = replace(catalog, harnesses=(wrong,) + catalog.harnesses[1:])
    result = select_route(changed, "summarize_ticket")
    assert "runtime_version_mismatch" in result["preferred"]["reasons"] and not result["execution_allowed"]


@pytest.mark.parametrize("config", [{}, {"providers": []}, {"providers": {"x": None}},
    {"active_provider": "x", "providers": {"x": {"cli_command": "shell", "fallback_providers": [{}], "model_chain": [{}, "ok"]}}}])
def test_malformed_legacy_values_fail_closed_without_default_or_shell(config):
    catalog = legacy_to_catalog(config, ["not-a-policy"])
    assert validate_references(catalog)
    assert not select_route(catalog, "draft_ticket")["execution_allowed"]


@pytest.fixture
def route_client(tmp_path, monkeypatch):
    from routes import providers as mod
    config = tmp_path / "providers.json";config.write_text(json.dumps(FIXTURE))
    (tmp_path / "config").mkdir()
    (tmp_path / "config/routing.yaml").write_text("enabled: true\ncombos: {R: [anthropic, omnirouter]}\n")
    monkeypatch.setattr(mod, "PROVIDERS_CONFIG", config)
    monkeypatch.setattr(mod, "WORKSPACE", tmp_path)
    def forbidden(*a, **k):raise AssertionError("unexpected side effect")
    monkeypatch.setattr(mod, "_read_config", forbidden)
    monkeypatch.setattr(mod, "_write_config", forbidden)
    monkeypatch.setattr(mod, "_run_cli_version", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    class User(UserMixin):
        def __init__(self, uid, role):self.id=uid;self.role=role
    app = Flask(__name__);app.config.update(SECRET_KEY="fixture-only",TESTING=True,SERVER_NAME="example.test")
    manager = LoginManager(app)
    @manager.user_loader
    def load(uid):return User(uid, "admin" if uid == "1" else "viewer")
    @app.before_request
    def token():g.auth_via_api_token = request.headers.get("X-Fixture-Token") == "yes"
    app.register_blueprint(mod.bp)
    client = app.test_client()
    def login(uid="1"):
        with client.session_transaction() as session:session["_user_id"]=uid;session["_fresh"]=True
    yield client, login, config, mod


def post(client, catalog, **updates):
    data = {"operation": "summarize_ticket", "expected_revision": catalog["catalog_revision"], **updates}
    return client.post("/api/execution/decisions/preview", json=data, base_url="https://example.test",headers={"Origin":"https://example.test"})


def test_api_is_read_only_no_env_loading_no_cli_network_files_or_jobs(route_client):
    client, login, path, _ = route_client;login();before=path.read_bytes();env=dict(os.environ)
    catalog = client.get("/api/execution/catalog")
    assert catalog.status_code == 200 and catalog.headers["Cache-Control"] == "no-store"
    assert client.get("/api/execution/templates").status_code == 200
    response = post(client, catalog.json)
    assert response.status_code == 200 and response.json["attempts"] == []
    assert path.read_bytes() == before and dict(os.environ) == env
    assert "PRIVATE" not in catalog.text + response.text


def test_auth_token_role_and_origin_rejected_before_catalog_reads(route_client):
    client, login, _, mod = route_client
    assert client.get("/api/execution/catalog").status_code == 401
    login("2");assert client.get("/api/execution/catalog").status_code == 403
    login();assert client.get("/api/execution/catalog",headers={"X-Fixture-Token":"yes"}).status_code == 403
    for origin in [None, "https://other.test", "http://example.test"]:
        h={"Origin":origin} if origin else {}
        assert client.post("/api/execution/decisions/preview",json={},base_url="https://example.test",headers=h).status_code == 403


@pytest.mark.parametrize("extra", [{"company_id":7}, {"ticketId":"private"}, {"prompt":"RUN"},
    {"command":"bash"}, {"user_id":1}, {"provider_key":"secret"}, {"selection":{"command":"bash"}}])
def test_preview_rejects_resource_tenant_command_and_credential_injection(route_client, extra):
    client,login,_,_=route_client;login()
    catalog=client.get("/api/execution/catalog").json
    assert post(client,catalog,**extra).status_code in (400,422)


def test_revision_conflict_requires_reload_and_invalid_operation_is_not_executable(route_client):
    client,login,path,_=route_client;login()
    catalog=client.get("/api/execution/catalog").json
    assert post(client,catalog,operation="publish").status_code==422
    assert post(client,catalog,pool_id=[]).status_code==422
    path.write_text(json.dumps({"active_provider":"none","providers":{}}))
    response=post(client,catalog)
    assert response.status_code==409 and response.json["reload_required"]


def test_missing_file_is_not_copied_or_repaired(route_client):
    client,login,path,_=route_client;login();path.unlink()
    catalog=client.get("/api/execution/catalog").json
    assert catalog["source_status"]=="unavailable" and not path.exists()
    assert post(client,catalog).json["preferred"] is None


def test_catalog_evidence_is_separate_from_runtime_attestation():
    h = legacy_to_catalog(FIXTURE).harnesses[0]
    assert h.proof_capabilities == ("text_generation", "no_tools")
    assert h.runtime_capabilities == () and h.runtime_version is None


def test_legacy_endpoints_still_use_the_existing_reader_and_masking(route_client, monkeypatch):
    client, login, _, mod = route_client;login()
    seen=[]
    def read():
        seen.append("legacy-reader")
        return copy.deepcopy(FIXTURE)
    monkeypatch.setattr(mod, "_read_config", read)
    assert client.get("/api/providers/active").json["active_provider"] == "omnirouter"
    response=client.get("/api/providers/omnirouter/config")
    assert response.status_code==200
    assert response.json["env_vars"]["OPENAI_API_KEY"] != "PRIVATE_KEY"
    assert seen == ["legacy-reader", "legacy-reader"]


@pytest.mark.parametrize("origin", ["https://[malformed", "https://user@example.test",
    "https://example.test/path", "https://example.test?x=1"])
def test_malformed_origin_never_500_or_accepts_non_origin_urls(route_client, origin):
    client, login, _, _=route_client;login()
    response=client.post("/api/execution/decisions/preview",json={},base_url="https://example.test",headers={"Origin":origin})
    assert response.status_code==403


@pytest.mark.parametrize("body", [[], None, {"operation":[]}, {"operation":"summarize_ticket","selection":[]},
    {"operation":"summarize_ticket","selection":{"provider_id":False}}])
def test_invalid_preview_shapes_do_not_execute(route_client, body):
    client,login,_,_=route_client;login()
    response=client.post("/api/execution/decisions/preview",json=body,base_url="https://example.test",headers={"Origin":"https://example.test"})
    assert response.status_code in (400,409,422)


def test_role_policy_kill_switch_preserves_active_pool_only(route_client,monkeypatch):
    client,login,_,_=route_client;login()
    assert len(client.get("/api/execution/catalog").json["pools"])==2
    monkeypatch.setenv("HEARTBEAT_ROUTING_POLICY","0")
    catalog=client.get("/api/execution/catalog").json
    assert [p["id"] for p in catalog["pools"]]==["legacy-active"]
    templates=client.get("/api/execution/templates").json
    assert templates["catalog_revision"]==catalog["catalog_revision"] and templates["default_pool"] is None


def test_invalid_files_are_never_rewritten_or_leak_error_contents(route_client):
    client,login,path,mod=route_client;login()
    path.write_text('PRIVATE_INVALID_JSON')
    (mod.WORKSPACE/'config/routing.yaml').write_text('PRIVATE_INVALID_YAML: [')
    before=path.read_bytes()
    catalog=client.get("/api/execution/catalog")
    assert catalog.status_code==200 and catalog.json["source_status"]=="unavailable"
    assert "PRIVATE_INVALID" not in catalog.text and path.read_bytes()==before
