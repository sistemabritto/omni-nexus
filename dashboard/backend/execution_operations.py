"""Configuration descriptors only; not an authorization/execution registry."""
OPERATIONS = {
    "party_turn": {
        "label": "Responder no Party Mode", "required_capabilities": ["text_generation", "no_tools"],
        "existing_adapter": "live_party", "side_effects": "internal_draft",
        "requires_resource_authorization": True,
    },
    "summarize_ticket": {
        "label": "Resumir ticket", "required_capabilities": ["text_generation", "no_tools"],
        "existing_adapter": "live_task_dispatch", "side_effects": "internal_draft",
        "requires_resource_authorization": True,
    },
    "draft_ticket": {
        "label": "Preparar rascunho interno", "required_capabilities": ["text_generation", "no_tools"],
        "existing_adapter": "live_task_dispatch", "side_effects": "internal_draft",
        "requires_resource_authorization": True,
    },
}


def execution_templates(catalog):
    """Adapt role combos; file/HTML/MD templates remain separate and untouched."""
    return {"version": 1, "catalog_revision": catalog.payload()["catalog_revision"], "source": "legacy-routing-projection",
            "templates": [{"id": p.id, "pool_id": p.id, "operations": list(OPERATIONS),
                           "required_capabilities": ["text_generation", "no_tools"],
                           "budget_status": "unknown", "execution_enabled": False}
                          for p in catalog.pools],
            "roles": dict(catalog.roles), "default_pool": catalog.default_combo}
