#!/usr/bin/env python3
"""Prepare a private, evidence-based recovery plan. Never sends messages.

OTP hashes, codes and IPs are deliberately not queried. Raw contacts remain in
the private local plan (0600); console output contains only counts and a digest.
"""
import argparse
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from growth_intelligence import load_env, request


def canonical(phone):
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    if digits.startswith('55') and len(digits) == 13 and int(digits[2:4]) >= 31 and int(digits[5]) >= 7:
        digits = digits[:4] + digits[5:]
    return '+' + digits if digits else ''


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def supabase(sql, write=False):
    route = '/database/query' if write else '/database/query/read-only'
    return request('POST', 'https://api.supabase.com/v1/projects/' + os.environ['SUPABASE_PROJECT_REF'] + route,
                   headers={'Authorization': 'Bearer ' + os.environ['SUPABASE_ACCESS_TOKEN']}, json={'query': sql})


def crm(sql):
    cid = subprocess.check_output(['ssh', 'evo-nexus-vps', 'docker ps --filter label=com.docker.swarm.service.name=pgvector_pgvector --format "{{.ID}}"'], text=True).strip()
    if not cid or '\n' in cid:
        raise RuntimeError('Expected exactly one CRM database container')
    command = f'docker exec -i {cid} psql -U postgres -d evocrm -Atq -v ON_ERROR_STOP=1'
    result = subprocess.run(['ssh', 'evo-nexus-vps', command], input=sql, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def prepare():
    otp = supabase("SELECT phone,min(created_at) first_seen,min(used_at) verified_at FROM public.otp_codes WHERE created_at < '2026-09-10' GROUP BY phone")
    existing = supabase("SELECT phone,email,source FROM public.leads")
    contact_phones = {canonical(r['phone']) for r in existing if r.get('phone')}
    emails = {r['email'].lower() for r in existing if r.get('email')}
    candidates = {}
    for row in otp:
        if row.get('verified_at'):
            candidates.setdefault(canonical(row['phone']), row)
    variants = set(candidates) | {'+' + r['phone'].lstrip('+') for r in candidates.values()}
    phones = ','.join(literal(p) for p in sorted(variants))
    rows = crm("BEGIN READ ONLY; SET LOCAL statement_timeout='15s'; SELECT coalesce(json_agg(t),'[]') FROM ("
               "SELECT c.id,c.name,c.email,c.phone_number,"
               "(SELECT count(*) FROM pipeline_items i LEFT JOIN conversations v ON v.id=i.conversation_id WHERE i.contact_id=c.id OR v.contact_id=c.id) opportunities "
               f"FROM contacts c WHERE c.phone_number IN ({phones or 'NULL'})"
               ") t; COMMIT;")
    contacts = {}
    ambiguous = set()
    for r in rows:
        key = canonical(r['phone_number'])
        if key in contacts:
            ambiguous.add(key)
        else:
            contacts[key] = r
    for key in ambiguous:
        contacts.pop(key, None)
    plan = []
    for phone, proof in candidates.items():
        contact = contacts.get(phone)
        email = (contact or {}).get('email') or f"whatsapp-{phone[1:]}@sem-email.sistemabritto.com.br"
        # Do not reinterpret old evidence as a new classroom conversion or new consent.
        plan.append({'phone': phone, 'original_phone': proof['phone'], 'first_seen': proof['first_seen'],
                     'verified_at': proof['verified_at'], 'contact': contact,
                     'email': email, 'ambiguous_crm_identity': phone in ambiguous,
                     'supabase_missing': phone not in contact_phones and email.lower() not in emails,
                     'crm_missing_opportunity': bool(contact and not contact['opportunities'])})
    return {'version': 1, 'cutoff': '2026-09-10', 'policy': 'no messages; no inferred campaign; verified OTP only',
            'ambiguous_crm_identities': len(ambiguous),
            'unverified_phones_excluded': sum(not row.get('verified_at') for row in otp), 'candidates': plan}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='tmp/legacy-lead-recovery-private.json')
    parser.add_argument('--apply-sha256')
    parser.add_argument('--rollback-test', action='store_true')
    args = parser.parse_args()
    load_env('.env')
    if args.apply_sha256:
        content = Path(args.output).read_bytes()
        if hashlib.sha256(content).hexdigest() != args.apply_sha256:
            raise RuntimeError('Recovery plan digest mismatch')
        result = apply(json.loads(content), rollback=args.rollback_test)
        print(json.dumps(result))
        return
    plan = prepare()
    content = json.dumps(plan, ensure_ascii=False, indent=2).encode()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content)
    rows = plan['candidates']
    print(json.dumps({'verified_candidates': len(rows), 'unverified_excluded': plan['unverified_phones_excluded'],
                      'ambiguous_crm_identities': plan['ambiguous_crm_identities'],
                      'supabase_missing': sum(r['supabase_missing'] for r in rows),
                      'crm_matched_contacts': sum(bool(r['contact']) for r in rows),
                      'crm_missing_opportunities': sum(r['crm_missing_opportunity'] for r in rows),
                      'sha256': hashlib.sha256(content).hexdigest()}))


def apply(plan, rollback=True):
    if plan['version'] != 1 or len(plan['candidates']) > 100:
        raise RuntimeError('Unexpected recovery plan')
    ending = 'ROLLBACK' if rollback else 'COMMIT'
    prepared = []
    for r in plan['candidates']:
        if not r['verified_at']:
            raise RuntimeError('Missing OTP evidence')
        if r['supabase_missing']:
            prepared.append({'phone': r['phone'], 'email': r['email'].lower(),
                             'name': (r['contact'] or {}).get('name') or 'Contato recuperado — nome não registrado',
                             'first_seen': r['first_seen'], 'verified_at': r['verified_at'],
                             'original_phone': r['original_phone']})
    data = literal(json.dumps(prepared))
    sb = supabase(f"""BEGIN; SET LOCAL statement_timeout='15s';
    WITH candidate AS (SELECT * FROM jsonb_to_recordset({data}::jsonb)
      AS x(phone text,email text,name text,first_seen timestamptz,verified_at timestamptz,original_phone text)),
    inserted AS (INSERT INTO public.leads (phone,email,name,source,created_at,answers)
      SELECT phone,email,name,'recovered-otp-unknown-origin',first_seen,
        jsonb_build_object('recovery_batch','20260910-legacy-otp','verified_at',verified_at,
          'original_phone',original_phone,'recovered_at',now(),'origin_known',false,'outreach_authorized',false)
      FROM candidate x WHERE NOT EXISTS (SELECT 1 FROM public.leads l WHERE lower(l.email)=x.email OR l.phone=x.phone)
      ON CONFLICT DO NOTHING RETURNING id)
    SELECT count(*) inserted FROM inserted; {ending};""", write=True)

    # Isolated manual-review pipeline. SQL deliberately avoids model callbacks
    # which broadcast stage-entry events and may send outbound messages.
    pipeline = str(uuid.uuid5(uuid.NAMESPACE_URL, 'sistemabritto/recovery/20260910/pipeline'))
    stage = str(uuid.uuid5(uuid.NAMESPACE_URL, 'sistemabritto/recovery/20260910/stage'))
    rows = [{'contact_id': r['contact']['id'], 'verified_at': r['verified_at'], 'first_seen': r['first_seen']}
            for r in plan['candidates'] if r['crm_missing_opportunity']]
    payload = literal(json.dumps(rows))
    cr = crm(f"""BEGIN; SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='5s';
    INSERT INTO pipelines (id,name,description,pipeline_type,created_by_id,custom_fields,config,visibility,created_at,updated_at)
      SELECT '{pipeline}','Recuperação de leads · revisão',
        'Contatos com OTP histórico verificado. Origem não comprovada. Sem disparos; revisar contexto antes de abordar.',
        'custom',created_by_id,'{{"attributes":[]}}','{{}}',visibility,now(),now()
      FROM pipelines WHERE id='eb72af5c-28f7-4948-ae50-9c81922d161e' ON CONFLICT DO NOTHING;
    INSERT INTO pipeline_stages (id,pipeline_id,name,position,stage_type,custom_fields,automation_rules,created_at,updated_at)
      VALUES ('{stage}','{pipeline}','Verificados · revisar antes de contato',1,0,'{{"attributes":[]}}','{{}}',now(),now())
      ON CONFLICT DO NOTHING;
    WITH candidate AS (SELECT * FROM jsonb_to_recordset({payload}::jsonb)
      AS x(contact_id uuid,verified_at timestamptz,first_seen timestamptz)),
    inserted AS (INSERT INTO pipeline_items
      (id,contact_id,pipeline_id,pipeline_stage_id,custom_fields,entered_at,created_at,updated_at)
      SELECT gen_random_uuid(),contact_id,'{pipeline}','{stage}',
        jsonb_build_object('recovery_batch','20260910-legacy-otp','source','recovered-otp-unknown-origin',
          'verified_at',verified_at,'first_seen',first_seen,'outreach_authorized',false),now(),now(),now()
      FROM candidate x WHERE EXISTS (SELECT 1 FROM contacts c WHERE c.id=x.contact_id)
      AND NOT EXISTS (SELECT 1 FROM pipeline_items i LEFT JOIN conversations v ON v.id=i.conversation_id
        WHERE i.contact_id=x.contact_id OR v.contact_id=x.contact_id)
      ON CONFLICT DO NOTHING RETURNING id),
    movements AS (INSERT INTO stage_movements
      (id,pipeline_item_id,to_stage_id,movement_type,notes,created_at,updated_at)
      SELECT gen_random_uuid(),id,'{stage}',2,'Recuperação histórica; não é nova conversão. Revisão manual, sem disparos.',now(),now()
      FROM inserted RETURNING id)
    SELECT json_build_object('opportunities_inserted',(SELECT count(*) FROM inserted),
      'movements_inserted',(SELECT count(*) FROM movements),'pipeline_id','{pipeline}'); {ending};""")
    return {'rollback': rollback, 'supabase': sb, 'crm': cr}


if __name__ == '__main__':
    main()
