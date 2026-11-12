import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard/backend"))
import sqlite3
from unittest.mock import patch

import runtime_preflight as preflight
import nexus_orchestrator
import heartbeat_runner


def test_preflight_reports_presence_never_values(tmp_path):
    env = {k: 'SECRET-SHOULD-NOT-LEAK' for k in ['EVONEXUS_API_URL', 'DASHBOARD_API_TOKEN', 'OPENREPLY_PG_HOST', 'OPENREPLY_PG_USER', 'OPENREPLY_PG_PASSWORD', 'OPENREPLY_PG_DB']}
    with patch.object(preflight.shutil, 'which', return_value=None):
        text = preflight.runtime_preflight(tmp_path, env=env)
    assert 'SECRET-SHOULD-NOT-LEAK' not in text
    assert 'Nexus API configurada: True' in text
    assert 'Postgres direto configurado: True' in text
    assert 'SSH disponível: False' in text
    assert 'não autoriza publicação' in text


def test_enabled_regular_heartbeat_wins_over_disabled_autopilot(tmp_path):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE heartbeats (id TEXT,agent TEXT,enabled INTEGER)')
    c.executemany('INSERT INTO heartbeats VALUES (?,?,?)', [('autopilot-nex', 'nex-sales', 0), ('nex-sales-4h', 'nex-sales', 1)])
    assert nexus_orchestrator._heartbeat_id_for_agent(c, 'nex-sales') == 'nex-sales-4h'
    text = preflight.runtime_preflight(tmp_path, env={}, conn=c)
    assert 'nex-sales (nex-sales-4h)' in text
    assert 'autopilot-nex' not in text
    c.execute('UPDATE heartbeats SET enabled=0')
    assert nexus_orchestrator._heartbeat_id_for_agent(c, 'nex-sales') is None


def test_prompt_allows_actual_research_and_explicit_nonpublication():
    text = heartbeat_runner.step6_assemble_context('identity', {'decision_prompt': 'task', 'runtime_preflight': 'verified runtime'}, None)
    assert 'Use ferramentas para ler' in text
    assert 'DECIDA AGORA' not in text
    assert 'verified runtime' in text
    assert 'publish_intent=false' in text


def test_sdk_default_endpoint_is_not_missing_credentials(tmp_path, monkeypatch):
    from sdk_client import EvoClient
    monkeypatch.delenv('EVONEXUS_API_URL', raising=False)
    monkeypatch.setenv('DASHBOARD_API_TOKEN', 'fixture-private-token')
    monkeypatch.setenv('FLASK_PORT', '8080')
    client = EvoClient()
    assert client.base_url == 'http://localhost:8080'
    assert client._session.headers.get('Authorization')
    text = preflight.runtime_preflight(tmp_path, env={'DASHBOARD_API_TOKEN':'fixture-private-token'})
    assert 'Nexus API configurada: True' in text
    assert 'fixture-private-token' not in text
    assert 'Endpoint customizado da API: False' in text
    assert 'não prova acesso entre containers' in text


def test_pg_defaults_and_runtime_interpreter_are_reported_without_probe(tmp_path):
    env = {'OPENREPLY_PG_PASSWORD': 'fixture-password'}
    with patch.object(preflight.importlib.util, 'find_spec', return_value=object()), patch('socket.socket.connect', side_effect=AssertionError('preflight must not open connections')):
        text = preflight.runtime_preflight(tmp_path, env=env)
    assert 'Postgres direto configurado: True' in text
    assert 'psycopg2 neste runtime: True' in text
    assert preflight.sys.executable in text
    assert 'fixture-password' not in text
    assert 'transação read-only' in text
    assert 'não ative campanha' in text


def test_system_python_missing_driver_does_not_hide_configured_access(tmp_path):
    with patch.object(preflight.importlib.util, 'find_spec', return_value=None):
        text = preflight.runtime_preflight(tmp_path, env={'OPENREPLY_DATABASE_URL':'fixture-private-dsn'})
    assert 'Postgres direto configurado: True' in text
    assert 'psycopg2 neste runtime: False' in text
    assert 'fixture-private-dsn' not in text
    assert 'python3 do sistema não comprova' in text
