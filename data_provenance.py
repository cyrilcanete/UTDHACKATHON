"""Read-only DataCite check for the bundled ESIF dataset's fixed public DOI.

This checks registration metadata, not the measurements or the facility. No
profile, sensor, account, or NVIDIA credential data belongs in this request.
"""
import json
import math
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DOI = '10.7799/3015212'
API_URL = 'https://api.datacite.org/dois/10.7799/3015212'
MAX_BYTES = 64 * 1024
MAX_SECONDS = 5.0
LIMITATION = ('This checks DOI registration metadata only. It does not verify measurement accuracy, '
              'refresh the historical excerpt, or establish live facility status.')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_HTTP = build_opener(_NoRedirect())


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _unavailable(reason, attempted_at=None, http_status=None):
    result = {'service': 'DataCite', 'api_url': API_URL, 'available': False,
              'status': 'unavailable', 'checked_at': None, 'attempted_at': attempted_at,
              'reason': reason, 'note': LIMITATION}
    if http_status is not None:
        result['http_status'] = http_status
    return result


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('Invalid metadata text')
    return ' '.join(value.split())


def _metadata(attributes):
    title = _text(attributes['titles'][0]['title'], 500)
    publisher = attributes['publisher']
    if isinstance(publisher, dict):
        publisher = publisher['name']
    publisher = _text(publisher, 300)
    year = attributes['publicationYear']
    if type(year) is not int or not 1000 <= year <= 9999:
        raise ValueError('Invalid publication year')
    updated = _text(attributes['updated'], 64)
    if datetime.fromisoformat(updated.replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Missing metadata timestamp timezone')
    landing = _text(attributes['url'], 2048)
    parsed = urlsplit(landing)
    if (parsed.scheme != 'https' or parsed.hostname not in ('www.osti.gov', 'osti.gov', 'data.nlr.gov')
            or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443)
            or any(character.isspace() for character in landing)):
        raise ValueError('Unexpected metadata landing page')
    if attributes['state'] != 'findable':
        raise ValueError('DOI record is not public')
    return {'doi': DOI, 'title': title, 'publisher': publisher, 'publication_year': year,
            'metadata_updated_at': updated, 'landing_page_url': landing}


def fetch_data_provenance(doi, *, deadline):
    """Fetch only the known public record, within the caller's workflow budget.

Failure is evidence too: return an explicit unavailable status without provider
response bodies or invented verification. Never follow metadata URLs or redirects.
"""
    if doi != DOI:
        return _unavailable('unsupported_dataset')
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        return _unavailable('invalid_time_budget')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return _unavailable('time_budget_exhausted')
    timeout = min(MAX_SECONDS, remaining)
    attempt_deadline = min(deadline, time.monotonic() + timeout)
    attempted_at = _stamp()
    request = Request(API_URL, method='GET', headers={
        'Accept': 'application/vnd.api+json',
        'User-Agent': 'SmartMirror/1.0 (https://github.com/cyrilcanete/UTDHACKATHON)',
    })
    try:
        with _HTTP.open(request, timeout=timeout) as response:
            if response.status != 200:
                return _unavailable('http_error', attempted_at, response.status)
            raw = response.read(MAX_BYTES + 1)
        if time.monotonic() >= attempt_deadline:
            return _unavailable('timeout', attempted_at)
        if len(raw) > MAX_BYTES:
            return _unavailable('response_too_large', attempted_at)
        record = json.loads(raw)['data']
        attributes = record['attributes']
        if record['id'] != DOI or attributes['doi'] != DOI:
            return _unavailable('doi_mismatch', attempted_at)
        metadata = _metadata(attributes)
    except HTTPError as error:
        reason = 'redirect_refused' if 300 <= error.code < 400 else 'http_error'
        return _unavailable(reason, attempted_at, error.code)
    except (TimeoutError, URLError, OSError) as error:
        reason = 'timeout' if isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError) else 'connection_failed'
        return _unavailable(reason, attempted_at)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return _unavailable('invalid_response', attempted_at)
    return {'service': 'DataCite', 'api_url': API_URL, 'available': True,
            'status': 'metadata_matched', 'checked_at': _stamp(), 'attempted_at': attempted_at,
            'note': LIMITATION, **metadata}
