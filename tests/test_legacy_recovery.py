import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from recover_legacy_leads import canonical, literal, apply


def test_normalizes_crm_brazilian_phone_representation():
    assert canonical('+55 (71) 99999-8888') == '+557199998888'
    assert canonical('+557199998888') == '+557199998888'


def test_preserves_sao_paulo_ninth_digit():
    assert canonical('+5511999998888') == '+5511999998888'


def test_sql_literal_escapes_quotes():
    assert literal("O'Connor") == "'O''Connor'"


def test_refuses_unverified_recovery_before_database_calls():
    with pytest.raises(RuntimeError, match='Missing OTP evidence'):
        apply({'version': 1, 'candidates': [{'verified_at': None}]})


def test_refuses_unexpected_bulk_scope():
    with pytest.raises(RuntimeError, match='Unexpected recovery plan'):
        apply({'version': 1, 'candidates': [{}] * 101})
