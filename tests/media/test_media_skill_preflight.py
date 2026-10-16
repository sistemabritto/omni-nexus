"""Use real scaffold/loader and deterministic provider fixtures, never a model."""
import hashlib
import json
from pathlib import Path
import pytest
import media_executor as executor
from media_retry import failure_state

ROOT = Path(__file__).resolve().parents[2]


def job(tmp_path):
    (tmp_path / 'input').mkdir()
    (tmp_path / 'input/job.json').write_text('{}')
    (tmp_path / 'output').mkdir()
    return tmp_path


def catalog(base):
    source = base / 'scoped-catalog'
    for relative in executor.REQUIRED_SKILL_DOCUMENTS:
        name = Path(relative).parts[-2]
        path = source / name / 'SKILL.md'
        path.parent.mkdir(parents=True)
        canonical = ROOT / '.claude' / ('skills' if name == 'social-media-production' else 'skills-media') / name / 'SKILL.md'
        path.write_bytes(canonical.read_bytes())
    return source


@pytest.mark.parametrize('state', ['missing', 'broken_link', 'empty', 'invalid_utf8', 'oversized'])
def test_skill_configuration_failure_never_invokes_model(tmp_path, monkeypatch, state):
    base = job(tmp_path)
    path = base / executor.REQUIRED_SKILL_DOCUMENTS[0]
    path.parent.mkdir(parents=True)
    if state == 'broken_link':
        path.symlink_to(base / 'missing')
    elif state == 'empty':
        path.write_text('  ')
    elif state == 'invalid_utf8':
        path.write_bytes(b'\xff')
    elif state == 'oversized':
        path.write_bytes(b'x' * 131073)
    monkeypatch.setattr(executor, 'invoke_with_fallback', lambda **_: pytest.fail('model forbidden'))
    with pytest.raises(executor.MediaExecutionError, match='Skill de produção indisponível') as error:
        executor.run_opencode_media_job(base)
    assert error.value.result['model_invoked'] is False
    assert failure_state(1, str(error.value)) == ('failed', None)


def test_real_scaffold_and_document_hashes_reach_provider_boundary(tmp_path, monkeypatch):
    import media_workspace
    source = catalog(tmp_path)
    monkeypatch.setenv('MEDIA_WORKSPACE', str(tmp_path / 'jobs'))
    monkeypatch.setenv('MEDIA_SKILLS_DIR', str(source))
    base = media_workspace.ensure_job_scaffold('15a2923d-977c-4426-9d0a-f41ced1e8423')
    (base / 'input/job.json').write_text('{}')
    calls = []
    def fixture_provider(**kwargs):
        calls.append(kwargs)
        (base / 'output/publication_manifest.json').write_text(json.dumps({'fixture': 'output, not real composition'}))
        return {'status': 'success'}
    monkeypatch.setattr(executor, 'invoke_with_fallback', fixture_provider)
    result = executor.run_opencode_media_job(base, force_provider='fixture-provider', force_model='fixture-model')
    assert len(calls) == 1
    call = calls[0]
    assert call['agent'] == '' and call['cwd'] == base
    assert call['force_provider'] == 'fixture-provider' and call['force_model'] == 'fixture-model'
    for relative in executor.REQUIRED_SKILL_DOCUMENTS:
        assert relative in call['prompt']
        row = next(x for x in result['skill_preflight']['documents'] if x['path'] == relative)
        assert row['sha256'] == hashlib.sha256((base / relative).read_bytes()).hexdigest()
    assert result['skill_preflight']['model_read_status'] == 'not_verified'
    assert result['skill_preflight']['application_status'] == 'not_verified'
    assert 'NÃO renderize' in call['prompt'] and 'sem publicar' in call['prompt']


def test_available_documents_do_not_turn_missing_output_into_delivery(tmp_path, monkeypatch):
    base = job(tmp_path)
    source = catalog(tmp_path)
    (base / '.claude').mkdir()
    (base / '.claude/skills').symlink_to(source, target_is_directory=True)
    monkeypatch.setattr(executor, 'invoke_with_fallback', lambda **_: {'status': 'success'})
    with pytest.raises(executor.MediaExecutionError, match='não produziu'):
        executor.run_opencode_media_job(base)
