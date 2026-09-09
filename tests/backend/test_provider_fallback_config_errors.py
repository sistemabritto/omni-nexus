import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard/backend"))
import provider_fallback as pf


def test_active_provider_with_empty_fallbacks_is_honored():
    config = {"active_provider": "gateway", "providers": {"gateway": {
        "model_chain": ["auto/reasoning"], "fallback_providers": [],
    }}}
    chain = pf._resolve_provider_chain(config)
    assert [p["provider_id"] for p in chain] == ["gateway"]
    assert chain[0]["model_chain"] == ["auto/reasoning"]


def test_unknown_fallback_does_not_replace_active_provider():
    config = {"active_provider": "gateway", "providers": {"gateway": {
        "model_chain": ["chosen-model"], "fallback_providers": ["missing"],
    }}}
    assert [p["provider_id"] for p in pf._resolve_provider_chain(config)] == ["gateway"]


def test_unconfigured_install_retains_default_chain():
    assert pf._resolve_provider_chain({}) == pf.DEFAULT_PROVIDER_CHAIN


def test_cli_error_envelope_preserves_provider_diagnostic(tmp_path):
    envelope = json.dumps({"type": "result", "is_error": True,
                           "result": "API Error: 410 model retired"})
    for code in (0, 1):
        result = pf._invoke_cli_run(
            [sys.executable, "-c", f"print({envelope!r}); raise SystemExit({code})"],
            {}, 5, tmp_path,
        )
        assert result["status"] == "fail"
        assert result["error"] == "API Error: 410 model retired"
