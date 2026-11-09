from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPCookieProcessor

BASE = 'https://ppubs.uspto.gov'


class LookupError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def normalize_numbers(query):
    numbers = []
    for part in re.split(r'[;；\n]+', query.strip()):
        value = re.sub(r'[\s,，]', '', part).upper()
        match = re.fullmatch(r'(?:US)?([0-9]{7,8})(B[12])?', value)
        if not match:
            raise LookupError('CONFIG_INVALID', 'Use US grant numbers separated by semicolons or newlines')
        number = match.group(1)
        if number not in numbers:
            numbers.append(number)
    return numbers


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {'p', 'h1', 'h2', 'h3', 'span', 'br'}:
            self.parts.append(' ')

    def handle_data(self, data):
        self.parts.append(data)


def plain(raw):
    parser = TextParser()
    parser.feed(raw)
    return ' '.join(''.join(parser.parts).split())


def labeled(raw, label):
    match = re.search(r'<p\b[^>]*>\s*' + re.escape(label) + r'\s*</p>\s*<p\b[^>]*>(.*?)</p>', raw, re.S | re.I)
    return plain(match.group(1)) if match else None


def parse_detail(doc, raw):
    if not isinstance(doc, dict) or not re.fullmatch(r'US-\d{7,8}-B[12]', doc.get('documentId', '')):
        raise LookupError('PARSE_ERROR', 'Unexpected USPTO document identifier')
    if doc['documentId'] not in raw or '<h2' not in raw:
        raise LookupError('PARSE_ERROR', 'USPTO detail page does not match the requested document')
    title = plain(doc.get('title', ''))
    if not title:
        raise LookupError('PARSE_ERROR', 'Patent title is missing')
    abstract = re.search(r'<h3\b[^>]*>\s*Abstract\s*</h3>\s*<p\b[^>]*>(.*?)</p>', raw, re.S | re.I)
    filed = labeled(raw, 'Filed:') or labeled(raw, 'Filed (or PCT Filed):')
    try:
        application_date = datetime.strptime(filed, '%B %d, %Y').date().isoformat() if filed else None
    except ValueError as exc:
        raise LookupError('PARSE_ERROR', 'Unrecognized USPTO filing date') from exc
    return {
        'external_id': doc['documentId'], 'patent_number': doc['patentNumber'],
        'kind_code': doc['documentId'].rsplit('-', 1)[1], 'title': title,
        'url': f"{BASE}/api/patents/html/{quote(doc['documentId'])}?source=USPAT",
        'summary': plain(abstract.group(1)) if abstract else None,
        'applicants': labeled(raw, 'Applicant:') or labeled(raw, 'Applicants:'),
        'assignees': labeled(raw, 'Assignee:') or labeled(raw, 'Assignees:'),
        'inventors': labeled(raw, 'Inventors:') or doc.get('inventors'),
        'application_number': labeled(raw, 'Appl. No.:'),
        'application_date': application_date, 'grant_date': doc.get('datePublished'),
        'source_site': 'uspto',
    }


class Client:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor())
        self.token = None
        self.last_request = 0

    def call(self, path, payload=None, as_json=True):
        headers = {'Accept': 'application/json' if as_json else 'text/html',
                   'User-Agent': 'Mozilla/5.0 crawler-package-platform/1.0'}
        if self.token:
            headers['x-access-token'] = self.token
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None:
            headers['Content-Type'] = 'application/json'
        for attempt in range(4):
            time.sleep(max(0, 5 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                with self.opener.open(Request(BASE + path, data=data, headers=headers), timeout=25) as response:
                    self.token = response.headers.get('x-access-token') or self.token
                    raw = response.read().decode('utf-8')
                    return json.loads(raw) if as_json else raw
            except HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    retry_after = exc.headers.get('Retry-After', '')
                    if retry_after.isdigit() and int(retry_after) > 30:
                        raise LookupError('RATE_LIMITED', 'USPTO requested a longer retry delay', True) from exc
                    time.sleep(int(retry_after) if retry_after.isdigit() else 10 * (attempt + 1))
                    continue
                code = 'AUTH_REQUIRED' if exc.code in (401, 403) else 'RATE_LIMITED' if exc.code == 429 else 'NETWORK_ERROR'
                raise LookupError(code, f'USPTO HTTP {exc.code}', exc.code == 429 or exc.code >= 500) from exc
            except (URLError, TimeoutError) as exc:
                raise LookupError('NETWORK_ERROR', 'USPTO request failed', True) from exc
            except (ValueError, UnicodeError) as exc:
                raise LookupError('PARSE_ERROR', 'USPTO returned an invalid response') from exc

    def lookup(self, number):
        if not self.token:
            self.call('/api/users/me/session', -1)
            if not self.token:
                raise LookupError('AUTH_REQUIRED', 'USPTO did not provide a public session')
        result = self.call('/api/searches/generic', {
            'cursorMarker': '*', 'databaseFilters': [{'databaseName': 'USPAT'}],
            'fields': ['documentId', 'patentNumber', 'title', 'datePublished', 'inventors', 'pageCount', 'type'],
            'op': 'OR', 'pageSize': 10, 'q': f'({number}).pn.', 'searchType': 0, 'sort': 'date_publ desc',
        })
        if not isinstance(result, dict) or not isinstance(result.get('docs'), list):
            raise LookupError('PARSE_ERROR', 'USPTO search response lacks docs')
        docs = [doc for doc in result['docs'] if str(doc.get('patentNumber')) == number]
        if not docs:
            raise LookupError('NOT_FOUND', f'US {number} was not found')
        doc = docs[0]
        raw = self.call('/api/patents/html/' + quote(doc['documentId']) + '?source=USPAT', as_json=False)
        return parse_detail(doc, raw)


def run(request, output):
    output.mkdir(parents=True, exist_ok=True)
    items, errors, warnings = [], [], []
    cursor, has_more = None, False
    try:
        numbers = normalize_numbers(request['query'])
        start = request.get('cursor') or 0
        if type(start) is not int or not 0 <= start < len(numbers):
            raise LookupError('CONFIG_INVALID', 'Invalid identifier cursor')
        client = Client()
        selected = numbers[start:start + request['limit']]
        for number in selected:
            try:
                item = client.lookup(number)
                items.append(item)
                missing = [name for name in ('summary', 'application_date', 'applicants', 'assignees') if not item[name]]
                if missing:
                    warnings.append({'code': 'FIELDS_MISSING', 'message': f'US {number}: missing ' + ', '.join(missing)})
            except LookupError as exc:
                errors.append({'code': exc.code, 'message': str(exc), 'retryable': exc.retryable})
        next_index = start + len(selected)
        has_more = next_index < len(numbers)
        cursor = next_index if has_more else None
        if any(request.get('time_range', {}).values()):
            warnings.append({'code': 'TIME_RANGE_NOT_SUPPORTED', 'message': 'Identifier lookup does not apply time_range filtering'})
    except LookupError as exc:
        errors.append({'code': exc.code, 'message': str(exc), 'retryable': exc.retryable})
    status = 'partial' if errors and items else 'failed' if errors else 'completed'
    if errors:
        cursor, has_more = None, False
        warnings.extend(errors[1:])
    with (output / 'items.jsonl').open('w', encoding='utf-8') as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + '\n')
    result = {'protocol_version': '1.0', 'execution_id': request['execution_id'], 'status': status,
              'item_count': len(items), 'next_cursor': cursor, 'has_more': has_more,
              'warnings': warnings, 'error': errors[0] if errors else None}
    temporary = output / 'result.json.tmp'
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temporary.replace(output / 'result.json')
    return 1 if status == 'failed' else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    return run(json.loads(Path(args.request).read_text(encoding='utf-8')), Path(args.output))


if __name__ == '__main__':
    sys.exit(main())
