"""Real isolated Flask handlers, synthetic files/cookies; no server/provider/credentials."""
import json
from pathlib import Path
import runpy
import tempfile

import pytest

suite = runpy.run_path("tests/backend/test_execution_catalog.py")
with tempfile.TemporaryDirectory(prefix="provider-contract-") as temporary:
    root = Path(temporary)
    patch = pytest.MonkeyPatch()
    patch.setenv("HEARTBEAT_ROUTING_POLICY", "1")  # fixture process only, restored below
    fixture = suite["route_client"].__wrapped__(root, patch)
    try:
        client, login, config, _ = next(fixture)
        (root / "config/routing.yaml").write_text(
            "enabled: true\ndefault_combo: REVIEW\n"
            "combos: {REVIEW: [anthropic, omnirouter]}\nroles: {oath: REVIEW}\n"
        )
        login()
        catalog = client.get("/api/execution/catalog")
        templates = client.get("/api/execution/templates")
        decision = suite["post"](client, catalog.json, pool_id="combo:REVIEW")
        assert all(response.status_code == 200 for response in (catalog, templates, decision))
        before = config.read_bytes()
        assert decision.json["provider_calls"] == 0 and decision.json["selected"] is None
        assert config.read_bytes() == before
        config.write_text(json.dumps({"active_provider": "none", "providers": {}}))
        conflict = suite["post"](client, catalog.json)
        assert conflict.status_code == 409
        disabled = client.get("/api/execution/catalog").json
        disabled_decision = suite["post"](client, disabled).json
        output = {"catalog": catalog.json, "templates": templates.json,
                  "decision": decision.json, "disabled": disabled,
                  "disabled_decision": disabled_decision, "conflict": conflict.json}
        assert "PRIVATE" not in json.dumps(output)
    finally:
        fixture.close()
        patch.undo()
print(json.dumps(output))
