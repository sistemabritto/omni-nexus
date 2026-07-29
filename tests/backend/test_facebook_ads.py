"""facebook_ads.coletar — mensageiro puro, sem interpretação. Mocka
requests.get, nunca bate na Graph API real.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import facebook_ads  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("META_ADS_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("META_ADS_ACCOUNT_IDS", "act_111,act_222")


def _resp(status_code, payload):
    r = MagicMock()
    r.status_code = status_code
    r.content = b"x"
    r.json.return_value = payload
    return r


def test_coletar_sem_token_levanta_erro(monkeypatch):
    monkeypatch.delenv("META_ADS_ACCESS_TOKEN", raising=False)
    with pytest.raises(facebook_ads.AdsIndisponivel):
        facebook_ads.coletar()


def test_coletar_sem_contas_configuradas_levanta_erro(monkeypatch):
    monkeypatch.delenv("META_ADS_ACCOUNT_IDS", raising=False)
    with pytest.raises(facebook_ads.AdsIndisponivel):
        facebook_ads.coletar()


def test_coletar_sem_campanha_ativa_devolve_lista_vazia():
    with patch.object(facebook_ads.requests, "get", return_value=_resp(200, {"data": []})):
        assert facebook_ads.coletar() == []


def test_coletar_normaliza_campanha_em_tres_metricas():
    payload = {"data": [{"campaign_name": "Campanha X", "spend": "12.50", "impressions": "1000", "clicks": "20"}]}
    with patch.object(facebook_ads.requests, "get", return_value=_resp(200, payload)):
        medicoes = facebook_ads.coletar()
    por_metrica = {(m["metrica"], m["origem"]): m["valor"] for m in medicoes}
    assert por_metrica[("ads_gasto", "campanha x")] == 12.5
    assert por_metrica[("ads_impressoes", "campanha x")] == 1000.0
    assert por_metrica[("ads_cliques", "campanha x")] == 20.0
    # duas contas configuradas, mesma resposta mockada pras duas -> 3 métricas x 2 contas
    assert len(medicoes) == 6


def test_coletar_conta_indisponivel_nao_derruba_as_outras():
    respostas = iter([_resp(400, {"error": {"message": "conta suspensa"}}),
                      _resp(200, {"data": [{"campaign_name": "Y", "spend": "1", "impressions": "1", "clicks": "1"}]})])

    def fake_get(url, params=None, timeout=None):
        return next(respostas)

    with patch.object(facebook_ads.requests, "get", side_effect=fake_get):
        medicoes = facebook_ads.coletar()
    assert len(medicoes) == 3
    assert medicoes[0]["origem"] == "y"
