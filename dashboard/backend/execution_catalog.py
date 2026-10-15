"""Read-only, nonsecret projection of legacy execution configuration.

No discovery, subprocess, credential resolution, provider calls or file writes.
This catalog describes configuration, not permission to execute.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

_ID = re.compile(r"^[A-Za-z0-9_.:/@+-]{1,200}$")


def identifier(value):
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def canonical_revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Harness:
    id: str
    adapter_id: str | None
    state: str
    runtime_version: str | None = None
    runtime_capabilities: tuple[str, ...] = ()
    proof_version: str | None = None
    proof_reference: str | None = None
    proof_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provider:
    id: str
    harness_id: str
    endpoint_ref: str
    auth_ref: str
    credential_status: str
    transport: str = "legacy_configured"


@dataclass(frozen=True)
class Model:
    id: str
    provider_id: str
    alias: str | None
    upstream_model: str | None = None
    cost_status: str = "unknown"
    capabilities_status: str = "unknown"


@dataclass(frozen=True)
class Route:
    harness_id: str
    provider_id: str
    model_id: str


@dataclass(frozen=True)
class Pool:
    id: str
    routes: tuple[Route, ...]


@dataclass(frozen=True)
class Catalog:
    active_provider: str | None
    source_status: str
    harnesses: tuple[Harness, ...]
    providers: tuple[Provider, ...]
    models: tuple[Model, ...]
    pools: tuple[Pool, ...]
    roles: tuple[tuple[str, str], ...]
    default_combo: str | None

    def payload(self):
        result = asdict(self)
        result["catalog_revision"] = canonical_revision(result)
        result["mode"] = "configuration_only"
        result["runtime_routing_changed"] = False
        return result


def legacy_to_catalog(config, routing=None, *, source_status="loaded"):
    """Preserve active/fallback/model ordering and role combos without mutating inputs.

    Missing active provider is unavailable, never the fallback engine's default chain.
    Endpoint/key values and arbitrary provider descriptions are deliberately excluded.
    Auth presence is unknown here: native stores/env/default-file resolvers are not read.
    """
    config = config if isinstance(config, dict) else {}
    routing = routing if isinstance(routing, dict) else {}
    raw = config.get("providers")
    raw = raw if isinstance(raw, dict) else {}
    harnesses = [
        Harness("opencode", "opencode_restricted_v1", "runtime_unverified",
                proof_version="1.17.18", proof_reference="qa/live-cli-isolation/runtime-proof.json",
                proof_capabilities=("text_generation", "no_tools")),
        Harness("claude", None, "legacy_only"),
        Harness("openclaude", None, "legacy_only"),
        Harness("hermes", None, "coming_soon"),
        Harness("codex", None, "coming_soon"),
    ]
    providers, models, routes = [], [], {}
    for pid, value in raw.items():
        if not identifier(pid) or not isinstance(value, dict):
            continue
        cli = value.get("cli_command", "openclaude")
        hid = cli if cli in {"opencode", "claude", "openclaude"} else "unsupported"
        providers.append(Provider(pid, hid, f"providers.json:providers.{pid}",
                                  f"existing-resolver:{pid}", "unknown"))
        env = value.get("env_vars")
        env = env if isinstance(env, dict) else {}
        chain = value.get("model_chain")
        if not isinstance(chain, list) or not chain:
            primary = value.get("default_model") or env.get("OPENAI_MODEL")
            chain = [primary] if identifier(primary) else []
            fallbacks = value.get("fallback_models")
            for alias in fallbacks if isinstance(fallbacks, list) else []:
                if identifier(alias) and alias not in chain:
                    chain.append(alias)
        if not chain and cli == "claude":
            chain = [None]
        routes[pid] = []
        for alias in chain:
            if alias is not None and not identifier(alias):
                continue
            mid = pid + ":" + (alias or "_legacy_default")
            if not any(m.id == mid for m in models):
                models.append(Model(mid, pid, alias))
            routes[pid].append(Route(hid, pid, mid))
    active = identifier(config.get("active_provider"))
    by_id = {p.id for p in providers}
    base = []
    if active in by_id and active != "none":
        base = [active]
        fallback = raw[active].get("fallback_providers")
        if isinstance(fallback, list):
            base.extend(pid for pid in fallback if isinstance(pid, str) and pid in by_id)
    pools = [Pool("legacy-active", tuple(r for pid in base for r in routes[pid]))]
    roles, default_combo = [], None
    if routing.get("enabled", True) is not False:
        combos = routing.get("combos")
        for name, order in (combos.items() if isinstance(combos, dict) else []):
            if not identifier(name) or not isinstance(order, list):
                continue
            # Existing combo semantics: inject configured providers, then active tail;
            # the existing reordering collapses provider duplicates.
            ordered = list(dict.fromkeys([pid for pid in order if isinstance(pid, str) and pid in by_id] + base))
            if active == "none" or active not in by_id:
                ordered = []
            pools.append(Pool("combo:" + name, tuple(r for pid in ordered for r in routes[pid])))
        known = {p.id for p in pools}
        mapping = routing.get("roles")
        for agent, combo in (mapping.items() if isinstance(mapping, dict) else []):
            if identifier(agent) and identifier(combo) and "combo:" + combo in known:
                roles.append((agent, "combo:" + combo))
        default = identifier(routing.get("default_combo"))
        default_combo = "combo:" + default if default and "combo:" + default in known else None
    return Catalog(active, source_status, tuple(harnesses), tuple(providers), tuple(models),
                   tuple(pools), tuple(roles), default_combo)


def validate_references(catalog):
    providers = {p.id: p for p in catalog.providers}
    models = {m.id: m for m in catalog.models}
    return all(r.provider_id in providers and r.model_id in models
               and models[r.model_id].provider_id == r.provider_id
               and providers[r.provider_id].harness_id == r.harness_id
               for pool in catalog.pools for r in pool.routes)
