#!/usr/bin/env python3
"""Read official public pages; retain changes locally. Never sign or transact."""
from __future__ import annotations
import argparse
import difflib
import fcntl
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'home': 'https://flop.finance/',
    'testnet': 'https://flop.finance/testnet/',
    'airdrop': 'https://flop.finance/airdrop/',
    'agent': 'https://flop.finance/intro/agent/',
    'yellowpaper': 'https://flop.finance/intro/yellowpaper/',
    'repositories': 'https://api.github.com/orgs/flop-labs/repos?per_page=100&type=public',
}

class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden:
            value = re.sub(r'\s+', ' ', data).strip()
            if value:
                self.parts.append(value)

def normalize(raw, key):
    if key == 'repositories':
        repos = json.loads(raw)
        if not isinstance(repos, list):
            raise ValueError('expected repository list')
        # Stars and download counters are noise; code/release activity is useful.
        fields = ('name', 'html_url', 'description', 'archived', 'pushed_at')
        return json.dumps([{k: r.get(k) for k in fields} for r in sorted(repos, key=lambda r: r['name'])], ensure_ascii=False, indent=2)
    parser = PageText()
    parser.feed(raw)
    value = '\n'.join(parser.parts)
    if len(value) < 80 or 'flop' not in value.lower():
        raise ValueError('unexpected page content; previous snapshot retained')
    return value

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect requires manual review')

def fetch(url):
    if url not in SOURCES.values():
        raise ValueError('source is not on the fixed official read-only list')
    request = urllib.request.Request(url, headers={'User-Agent': 'flop-readiness-watch/1.0', 'Accept': 'text/html,application/json'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f'unexpected HTTP status {response.status}')
        body = response.read(4_000_001)
        if len(body) > 4_000_000:
            raise ValueError('response too large')
        return body.decode('utf-8')

def write_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)

def check(directory, fetcher=fetch):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_file = directory / 'state.json'
        state = json.loads(state_file.read_text()) if state_file.exists() else {'sources': {}, 'events': []}
        now = datetime.now(timezone.utc).isoformat()
        results = []
        for key, url in SOURCES.items():
            old = state['sources'].get(key, {})
            try:
                content = normalize(fetcher(url), key)
                digest = hashlib.sha256(content.encode()).hexdigest()
                snapshot = directory / f'{key}.txt'
                event = 'baseline' if not old else ('changed' if digest != old['sha256'] else 'unchanged')
                if event != 'unchanged':
                    before = snapshot.read_text() if snapshot.exists() else ''
                    if event == 'changed':
                        diff = '\n'.join(difflib.unified_diff(before.splitlines(), content.splitlines(), fromfile=key+' before', tofile=key+' after'))
                        (directory / f'{key}.diff').write_text(diff + '\n')
                        state['events'].append({'at': now, 'source': key, 'url': url, 'diff': f'{key}.diff'})
                    snapshot.write_text(content)
                state['sources'][key] = {'url': url, 'sha256': digest, 'last_success': now, 'last_change': now if event != 'unchanged' else old['last_change']}
                results.append({'source': key, 'status': event})
            except Exception as error:
                # Errors never erase the last successful content or count as a change.
                results.append({'source': key, 'status': 'error', 'error': f'{type(error).__name__}: {error}'})
        state['events'] = state['events'][-100:]
        state['last_check'] = now
        state['results'] = results
        write_json(state_file, state)
        lines = ['# FLOP公式更新チェック', '', f'最終確認（UTC）: {now}', '', '変化は要確認の通知です。開始・配布資格を自動判定しません。', '', '| ページ | 今回 | 最後の取得成功（UTC） |', '|---|---|---|']
        for result in results:
            key = result['source']
            lines.append(f"| {key} | {result['status']} | {state['sources'].get(key, {}).get('last_success', '未取得')} |")
        lines += ['', '## 保存された変更通知（直近100件）', '']
        lines += [f"- {e['at']} [{e['source']}]({e['url']}) — {e['diff']}（各ページの最新差分）" for e in state['events']]
        if not state['events']:
            lines.append('変更通知はまだありません。初回は比較基準を保存します。')
        for result in results:
            if result['status'] == 'error':
                lines.append(f"\n取得失敗 {result['source']}: {result['error']}")
        (directory / 'REPORT.md').write_text('\n'.join(lines) + '\n')
        return {'checked_at': now, 'results': results, 'retained_change_events': len(state['events']), 'report': str(directory / 'REPORT.md')}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'status'])
    args = parser.parse_args()
    directory = ROOT / 'monitor'
    if args.command == 'status':
        path = directory / 'state.json'
        print(path.read_text() if path.exists() else '{"status":"not-yet-checked"}')
        return 0
    try:
        result = check(directory)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(any(r['status'] == 'error' for r in result['results']))

if __name__ == '__main__':
    raise SystemExit(main())
