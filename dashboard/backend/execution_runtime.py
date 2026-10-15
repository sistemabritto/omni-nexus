"""Opt-in internal text routing through the EXISTING restricted OpenCode adapter.

No generic executor. Policy files are operator-owned attestations, not model input.
No provider invocation on import, catalog listing, preview or planning.
"""
import copy
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
from urllib.parse import urlsplit

from flask import current_app
from execution_catalog import canonical_revision, legacy_to_catalog
from execution_operations import OPERATIONS

PROOF_VERSION = "1.17.18"
PROOF_SHA256 = "0cbfb6de55aa4ce3c74da12d8516376033693a88abca6238c5be32bf98130636"


def enabled():
    return current_app.config.get("NEXUS_EXECUTION_ROUTING_ENABLED") is True


def _json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _attest_binary():
    """Hash, never execute, the installed binary against the committed adapter proof."""
    binary = shutil.which("opencode")
    if not binary:
        return False
    try:
        digest = hashlib.sha256()
        with open(binary, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == PROOF_SHA256
    except OSError:
        return False


def _load():
    import provider_fallback as pf
    import yaml
    config = _json(pf.PROVIDERS_CONFIG)
    routing = {}
    if os.environ.get("HEARTBEAT_ROUTING_POLICY", "1").lower() not in ("0", "false", "no"):
        try:
            routing = yaml.safe_load(pf.ROUTING_CONFIG.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError, yaml.YAMLError):
            pass
    catalog = legacy_to_catalog(config, routing)
    path = current_app.config.get("NEXUS_EXECUTION_POLICY_PATH") or pf.WORKSPACE / "config/execution-policy.json"
    policy = _json(path)
    return config, catalog, policy


def plan(operation, agent_name):
    """Resolve routes and prerequisites; no CLI/provider call, queue or file write."""
    config, catalog, policy = _load()
    revision = catalog.payload()["catalog_revision"]
    # Only fixed schema is used; arbitrary operator keys never reach telemetry.
    policy_keys = {"version", "catalog_revision", "expires_at", "models", "max_attempts", "timeout_seconds"}
    clean = {k: policy.get(k) for k in policy_keys}
    reasons = []
    valid = (type(policy.get("version")) is int and policy.get("version") == 1
             and policy.get("catalog_revision") == revision)
    try:
        valid = valid and datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except (KeyError, ValueError, TypeError, AttributeError):
        valid = False
    limit, timeout = policy.get("max_attempts"), policy.get("timeout_seconds")
    if type(limit) is not int or not 1 <= limit <= 3 or type(timeout) is not int or not 20 <= timeout <= 120:
        valid = False
    if not valid:
        reasons.append("policy_missing_expired_or_invalid")
    if operation not in OPERATIONS:
        reasons.append("operation_unsupported")
    if catalog.active_provider == "none":
        reasons.append("active_provider_disabled")
    pool_id = dict(catalog.roles).get(agent_name) or catalog.default_combo or "legacy-active"
    pool = next(p for p in catalog.pools if p.id == pool_id)
    models = {m.id: m for m in catalog.models}
    binary_ok = _attest_binary() if valid else False
    candidates, eligible, guards = [], [], []
    import provider_fallback as pf
    windows = pf._availability_windows()
    raw_providers = config.get("providers", {})
    declarations = policy.get("models") if isinstance(policy.get("models"), dict) else {}
    for route in pool.routes:
        why = []
        model = models[route.model_id]
        if (route.provider_id in windows or pf.is_on_cooldown(route.provider_id)
                or pf.is_on_cooldown(route.provider_id + ":" + str(model.alias))):
            why.append("provider_temporarily_unavailable")
        provider = raw_providers[route.provider_id]
        env = provider.get("env_vars") if isinstance(provider.get("env_vars"), dict) else {}
        endpoint = provider.get("default_base_url") or env.get("OPENAI_BASE_URL")
        try:
            u = urlsplit(endpoint) if isinstance(endpoint, str) else None
            safe_endpoint = bool(u and u.scheme in ("http", "https") and u.hostname and not (
                u.username or u.password or u.query or u.fragment))
        except ValueError:
            safe_endpoint = False
        credential_present = bool(pf._get_api_key(route.provider_id, config)) if safe_endpoint else False
        guards.append({"route":route.model_id,"endpoint":endpoint if safe_endpoint else None,"credential_present":credential_present})
        if route.harness_id != "opencode":
            why.append("restricted_adapter_unsupported")
        if not binary_ok:
            why.append("adapter_binary_unverified")
        if not safe_endpoint or not credential_present or not model.alias:
            why.append("explicit_provider_unavailable")
        attestation = declarations.get(route.model_id, {})
        if not isinstance(attestation, dict):
            attestation = {}
        caps = attestation.get("verified_capabilities")
        ref = attestation.get("evidence_ref")
        if (not isinstance(caps, list) or "text_generation" not in caps
                or not isinstance(ref, str) or not ref.strip() or len(ref) > 300):
            why.append("model_capabilities_unknown")
        cost = attestation.get("max_cost_per_attempt_usd")
        budget = attestation.get("approved_budget_usd")
        numbers = all(type(v) in (int, float) and 0 <= v <= 1_000_000 and math.isfinite(v) for v in (cost, budget))
        if not numbers or not valid or cost * limit > budget:
            why.append("budget_unverified")
        item = {"harness_id":route.harness_id,"provider_id":route.provider_id,"model_id":route.model_id,
                "model":model.alias,"eligible":not why and not reasons,"reasons":why}
        candidates.append(item)
        if item["eligible"]:
            eligible.append(item)
    if not eligible:
        reasons.append("no_eligible_route")
    # Digests contain no prompts/outputs/credential values. Endpoint guard detects
    # endpoint change; credential presence (not secret rotation) is revalidated.
    state = {"catalog_revision":revision,"policy_revision":canonical_revision(clean),
             "configuration_revision":canonical_revision(guards),"binary_verified":binary_ok,
             "pool_id":pool_id,"candidates":candidates,"reasons":reasons,
             "max_attempts":limit if valid else 0,"timeout_seconds":timeout if valid else 0,
             "model_capabilities_source":"operator_attestation",
             "intended":eligible[0] if eligible else None,
             "eligible_routes":eligible[:limit] if valid else [],"attempts":[],
             "status":"planned" if eligible else "blocked","realized":None}
    state["plan_revision"] = canonical_revision(state)
    return state


def execute(planned, operation, agent_name, prompt, cwd, authorize, persist):
    """Existing worker owns claim/idempotency. Every attempt is durable before call.

    No implicit legacy/default fallback. A crash leaves attempt status=started and
    must be reconciled manually; this function never replays an existing attempt.
    """
    import provider_fallback as pf
    if planned.get("attempts"):
        raise ValueError("execution_attempt_already_started")
    fresh = plan(operation, agent_name)
    state = copy.deepcopy(planned)
    if not enabled() or fresh["plan_revision"] != planned["plan_revision"]:
        state.update(status="blocked", reasons=["execution_plan_changed"])
        persist(state)
        return {"status":"fail","output":"","route_trace":state}
    if not fresh["eligible_routes"]:
        persist(state)
        return {"status":"fail","output":"","route_trace":state}
    deadline = time.monotonic() + fresh["timeout_seconds"]
    previous_reason = None
    for route in fresh["eligible_routes"]:
        authorize()  # cancellation, tenant/agent/resource ACL and input revision
        if not enabled() or plan(operation, agent_name)["plan_revision"] != planned["plan_revision"]:
            state.update(status="blocked",reasons=["execution_plan_changed"]);persist(state);break
        remaining = int(deadline-time.monotonic())
        if remaining < 1:
            state.update(status="failed",reasons=["execution_deadline"]);persist(state);break
        attempt = {"ordinal":len(state["attempts"])+1,"intended":{k:route[k] for k in ("harness_id","provider_id","model_id")},
                   "status":"started","fallback_reason":previous_reason,"realized":None}
        state["attempts"].append(attempt);state["status"]="running";persist(state)
        config, _, _ = _load()
        provider = config["providers"][route["provider_id"]]
        env = provider.get("env_vars") or {}
        selected_env = {"OPENAI_BASE_URL":provider.get("default_base_url") or env.get("OPENAI_BASE_URL"),
                        "OPENAI_API_KEY":pf._get_api_key(route["provider_id"], config)}
        started = time.monotonic()
        try:
            token=pf._CLI_TOOL_POLICY.set("no_tools")
            try:
                result=pf._invoke_cli("opencode",prompt,2,remaining,agent="",cwd=cwd,
                    env_overrides=selected_env,provider_id=route["provider_id"],model=route["model"])
            finally:
                pf._CLI_TOOL_POLICY.reset(token)
            success = result.get("status") == "success" and isinstance(result.get("output"),str) and bool(result["output"].strip())
            status = "provider_success" if success else ("timeout" if result.get("status")=="timeout" else "provider_failed")
        except Exception:
            result={};success=False;status="adapter_exception"
        attempt.update(status=status,elapsed_ms=int((time.monotonic()-started)*1000))
        # Passing a tuple into a CLI is not independent upstream-model evidence.
        attempt["adapter_invoked"] = "opencode_restricted_v1"
        previous_reason = status
        if success:
            state.update(status="provider_success")
        persist(state)
        authorize()  # revalidate before retry/return; caller also serializes delivery
        if not enabled() or plan(operation, agent_name)["plan_revision"] != planned["plan_revision"]:
            state.update(status="blocked", reasons=["execution_plan_changed"])
            persist(state)
            return {"status":"fail","output":"","route_trace":state}
        if success:
            return {"status":"success","output":result["output"],"provider_id":route["provider_id"],
                    "model":route["model"],"cli_command":"opencode","attempt_number":attempt["ordinal"],"route_trace":state}
    if state["status"]=="running":
        state["status"]="failed";state["reasons"]=["routes_exhausted"];persist(state)
    return {"status":"fail","output":"","route_trace":state}
