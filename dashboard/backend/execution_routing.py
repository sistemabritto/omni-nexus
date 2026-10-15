"""Deterministic configuration preview. Cannot invoke a harness/provider or queue work."""
from dataclasses import asdict
from execution_catalog import canonical_revision
from execution_operations import OPERATIONS


def select_route(catalog, operation, *, pool_id="legacy-active", selection=None):
    if operation not in OPERATIONS:
        raise ValueError("unsupported_operation")
    pool = next((p for p in catalog.pools if p.id == pool_id), None)
    if pool is None:
        raise ValueError("unknown_pool")
    selection = selection or {}
    if set(selection) - {"harness_id", "provider_id", "model_id"}:
        raise ValueError("invalid_selection")
    harnesses = {h.id: h for h in catalog.harnesses}
    candidates = []
    for ordinal, route in enumerate(pool.routes, 1):
        reasons = []
        item = asdict(route)
        if any(item[k] != v for k, v in selection.items()):
            reasons.append("selection_mismatch")
        harness = harnesses.get(route.harness_id)
        if harness is None or harness.adapter_id != "opencode_restricted_v1":
            reasons.append("restricted_adapter_unsupported")
        else:
            # A repository proof is not a current installation/version attestation.
            if harness.runtime_version is None:
                reasons.append("runtime_version_unknown")
            elif harness.runtime_version != harness.proof_version:
                reasons.append("runtime_version_mismatch")
            for capability in OPERATIONS[operation]["required_capabilities"]:
                if capability not in harness.runtime_capabilities:
                    reasons.append("capability_unverified:" + capability)
        reasons += ["credential_resolution_not_performed", "model_capabilities_unknown", "budget_unknown"]
        candidates.append({"ordinal": ordinal, **item, "eligible": False, "reasons": reasons})
    preferred = next((c for c in candidates if "selection_mismatch" not in c["reasons"]), None)
    payload = catalog.payload()
    result = {"mode": "preview", "operation": operation, "pool_id": pool_id,
              "catalog_revision": payload["catalog_revision"], "policy_revision": payload["catalog_revision"],
              "selection": selection, "preferred": preferred, "selected": None,
              "candidates": candidates, "attempts": [], "execution_allowed": False,
              "scope": "configuration_only", "resource_authorization": "not_evaluated",
              "runtime_routing_changed": False, "provider_calls": 0,
              "reasons": ["preview_only", "resource_authorization_not_evaluated", "runtime_policy_not_connected"]}
    if catalog.active_provider == "none":
        result["reasons"].append("active_provider_disabled")
    elif not candidates:
        result["reasons"].append("no_configured_route")
    if selection and preferred is None:
        result["reasons"].append("selection_not_in_pool")
    # Stable fingerprint is explicitly not a persisted/authorized execution decision.
    result["preview_fingerprint"] = canonical_revision(result)
    return result
