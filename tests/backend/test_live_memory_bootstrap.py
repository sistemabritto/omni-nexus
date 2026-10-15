"""Real authorized context routes, synthetic two-company records; no provider."""
from tests.backend.test_managed_live_context import setup, create, link, read
import pytest


def test_enabled_bootstrap_includes_bounded_identity_and_owned_completed_sample(setup, tmp_path):
    app, client, login, mod, _, _ = setup
    from models import db, Ticket
    (mod.AGENTS_DIR/'agent-a.md').write_text('ROLE_A\n'+'x'*3000+'\n# Persistent Agent Memory\nPRIVATE_MEMORY')
    with app.app_context():
        for i in range(5):
            db.session.add(Ticket(id=f'a{i}', company_id=7, title='Prior A', description='Owned output', status='resolved', priority='medium', created_by='fixture', created_at='2026-01-01', updated_at='2026-01-02'))
        for tid, company in [('other', 8), ('legacy', None)]:
            db.session.add(Ticket(id=tid, company_id=company, title='SECRET_OTHER', status='resolved', priority='medium', created_by='fixture', created_at='2026-01-01', updated_at='2026-01-02'))
        db.session.commit()
    login();ctx=create(client).json;link(client,ctx['contextId'])
    disabled=read(client,ctx['contextId'])
    assert 'agentIdentity' not in disabled.json and 'previousWork' not in disabled.json
    app.config.update(NEXUS_LIVE_CONTINUITY_ENABLED=True,NEXUS_LIVE_CONTINUITY_DB=str(tmp_path/'continuity.db'))
    result=read(client,ctx['contextId'])
    assert result.status_code==200
    identity=result.json['agentIdentity']
    assert identity['persona'].startswith('ROLE_A') and len(identity['persona'])==2500
    assert identity['truncated'] and identity['legacyMemoryImported'] is False
    assert 'PRIVATE_MEMORY' not in result.text and 'SECRET_OTHER' not in result.text
    work=result.json['previousWork']
    assert work['coverage']=='completed_ticket_sample_only' and len(work['results'])==3
    assert all(x['reference'].startswith('/api/tickets/a') and x['comments']==[] for x in work['results'])


def test_catalog_identity_never_reads_symlink_outside_catalog(setup, tmp_path):
    app, client, login, mod, _, _ = setup
    secret=tmp_path/'outside.md';secret.write_text('NEVER_RETURN_THIS')
    (mod.AGENTS_DIR/'agent-a.md').unlink();(mod.AGENTS_DIR/'agent-a.md').symlink_to(secret)
    app.config.update(NEXUS_LIVE_CONTINUITY_ENABLED=True,NEXUS_LIVE_CONTINUITY_DB=str(tmp_path/'continuity.db'))
    login();ctx=create(client).json;link(client,ctx['contextId'])
    response=read(client,ctx['contextId'])
    assert response.status_code==503 and 'NEVER_RETURN_THIS' not in response.text


@pytest.mark.parametrize('marker', ['# Persistent Agent Memory', '## MEMORY.md'])
def test_short_persona_excludes_persistent_memory_even_inside_budget(setup, tmp_path, marker):
    app, client, login, mod, _, _ = setup
    (mod.AGENTS_DIR/'agent-a.md').write_text('ROLE_A\n'+marker+'\nPRIVATE_MEMORY')
    app.config.update(NEXUS_LIVE_CONTINUITY_ENABLED=True,NEXUS_LIVE_CONTINUITY_DB=str(tmp_path/'continuity.db'))
    login();ctx=create(client).json;link(client,ctx['contextId'])
    result=read(client,ctx['contextId'])
    assert result.status_code==200 and result.json['agentIdentity']['persona']=='ROLE_A\n'
    assert 'PRIVATE_MEMORY' not in result.text
