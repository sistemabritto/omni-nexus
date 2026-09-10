#!/usr/bin/env python3
"""Read-only publication evidence; no captions, contacts, DM or publishing calls."""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from growth_intelligence import load_env, request


def collect():
    now = datetime.now(timezone.utc)
    start = datetime(2026, 9, 11, 3, tzinfo=timezone.utc)
    end = start + timedelta(days=30)
    token = os.environ['SOCIAL_INSTAGRAM_1_ACCESS_TOKEN']
    account = os.environ['SOCIAL_INSTAGRAM_1_ACCOUNT_ID']
    base = 'https://graph.instagram.com/v23.0' if token.startswith('IG') else 'https://graph.facebook.com/v25.0'
    rows, after, complete = [], None, False
    for _ in range(6):
        params = {'fields': 'id,media_product_type,timestamp,permalink', 'limit': 100}
        if after:
            params['after'] = after
        page = request('GET', f'{base}/{account}/media', headers={'Authorization': 'Bearer '+token}, params=params)
        batch = page.get('data', [])
        rows.extend(r for r in batch if start <= datetime.fromisoformat(r['timestamp']) < end)
        paging = page.get('paging', {})
        after = paging.get('cursors', {}).get('after') if paging.get('next') else None
        if not after or not batch or min(datetime.fromisoformat(r['timestamp']) for r in batch) < start:
            complete = True
            break
    return {'collected_at': now.isoformat(), 'start_inclusive': start.isoformat(),
            'end_exclusive': min(now, end).isoformat(), 'sources': {'instagram': {'status': 'ok',
            'data': {'media': rows, 'pagination_truncated': not complete}}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    load_env(args.env)
    target = Path(args.output)
    report = collect()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps({'status': 'ok', 'media_count': len(report['sources']['instagram']['data']['media']),
                      'complete': not report['sources']['instagram']['data']['pagination_truncated']}))


if __name__ == '__main__':
    main()
