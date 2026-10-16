"""Contract evidence only: fixtures are not an audiovisual review performed."""
import copy
import pytest
from media_creative_review import CRITERIA, METHODS, validate_creative_review, creative_review_eligible

HASH = 'a' * 64
VERSION = 'render-v1'


def evidence(kind='frame'):
    row = {'kind': kind, 'ref': 'output/review/frame-001.png', 'sha256': 'b' * 64}
    if kind in ('audio_range', 'time_range'):
        row.update(start=0, end=1)
    return row


def sample():
    return {'render_sha256': HASH, 'version_id': VERSION, 'duration_seconds': 5,
            'brand_reference': {'source': 'input/brand/approved-brief.md', 'version': 'fixture-v1'},
            'methods': {name: {'source': source, 'version': version, 'application': 'Fixture observations by criterion; not a real review'}
                        for name, (source, version) in METHODS.items()},
            'criteria': {name: {'status': 'PASS', 'observation': 'Fixture observation; not actual audiovisual evidence',
                                'reason': '', 'evidence': [evidence('audio_range' if name == 'audio' else 'frame')]}
                         for name in CRITERIA}, 'findings': []}


def validate(data):
    return validate_creative_review(data, render_sha256=HASH, version_id=VERSION)


def test_valid_claim_is_normalized_without_mutation_and_eligible_is_not_approval():
    data = sample(); prior = copy.deepcopy(data)
    result = validate(data)
    assert data == prior and result == prior
    assert creative_review_eligible(result)
    assert 'approved' not in result and 'reviewer' not in result


@pytest.mark.parametrize('field,value', [('render_sha256', 'c'*64), ('version_id', 'render-v2'), ('duration_seconds', 0), ('duration_seconds', float('nan'))])
def test_changed_render_version_or_invalid_duration_cannot_reuse_claim(field, value):
    data = sample(); data[field] = value
    with pytest.raises(ValueError): validate(data)


@pytest.mark.parametrize('key', ['reviewer', 'approved', 'human_approval', 'eligible'])
def test_no_client_identity_or_approval_field(key):
    data = sample(); data[key] = True
    with pytest.raises(ValueError): validate(data)


@pytest.mark.parametrize('status', ['FAIL', 'NOT_TESTED'])
def test_nonpassing_review_recordable_but_ineligible(status):
    data = sample(); data['criteria']['rhythm'].update(status=status, reason='requires actual playback')
    assert not creative_review_eligible(validate(data))


def test_na_needs_reason_and_brand_cannot_be_exempted():
    data = sample(); data['criteria']['captions'].update(status='NOT_APPLICABLE', reason='No speech or caption content in approved scope', evidence=[])
    assert creative_review_eligible(validate(data))
    data['criteria']['captions']['reason'] = ''
    with pytest.raises(ValueError): validate(data)
    data = sample(); data['criteria']['identity'].update(status='NOT_APPLICABLE', reason='fixture')
    assert not creative_review_eligible(validate(data))


@pytest.mark.parametrize('ref', ['/tmp/frame.png', '../frame.png', 'output/../frame.png', 'https://example.com/x', 'output\\x.png', 'output//x.png', 'output/\x00.png'])
def test_evidence_must_be_unambiguous_local_reference(ref):
    data = sample(); data['criteria']['composition']['evidence'][0]['ref'] = ref
    with pytest.raises(ValueError): validate(data)


@pytest.mark.parametrize('start,end', [(2,1),(-1,1),(0,6),(0,float('inf')),(True,1)])
def test_temporal_evidence_within_claimed_duration(start,end):
    data = sample(); data['criteria']['audio']['evidence'][0].update(start=start,end=end)
    with pytest.raises(ValueError): validate(data)


@pytest.mark.parametrize('severity,eligible', [('P0',False),('P1',False),('P2',True)])
def test_findings_stay_visible_and_blockers_block(severity,eligible):
    data = sample(); data['findings'] = [{'id':'f1','criterion':'composition','severity':severity,
        'status':'open','description':'Fixture issue','resolution':'','evidence':[evidence()]}]
    assert creative_review_eligible(validate(data)) is eligible
    data['findings'][0].update(status='resolved',resolution='Fixture retest',evidence=[])
    with pytest.raises(ValueError): validate(data)
    data['findings'][0]['evidence'] = [evidence()]
    assert creative_review_eligible(validate(data))


def test_method_names_alone_are_insufficient():
    data = sample(); data['methods']['taste']['application'] = ''
    with pytest.raises(ValueError): validate(data)
    data = sample(); data['methods']['anti_slop']['version'] = 'unknown'
    with pytest.raises(ValueError): validate(data)
    data = sample(); data['criteria']['legibility']['evidence'] = []
    with pytest.raises(ValueError): validate(data)
    assert not creative_review_eligible({'approved': True})
