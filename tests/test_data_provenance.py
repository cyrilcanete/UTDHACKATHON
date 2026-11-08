"""DataCite protocol and tool integration tests; external HTTP is always mocked."""
import copy
import io
import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import data_provenance as provenance
from configure_nemotron import smoke_assessment
from nemotron_agent import NAMES, NemotronError, run


RECORD = {'data': {'id': provenance.DOI, 'attributes': {
    'doi': provenance.DOI, 'titles': [{'title': 'NLR HPC Facility Power Usage Effectiveness (PUE) Data'}],
    'publisher': 'National Laboratory of the Rockies', 'publicationYear': 2025,
    'updated': '2026-01-29T18:43:32.000Z', 'state': 'findable',
    'url': 'https://www.osti.gov/servlets/purl/3015212', 'xml': 'UNNEEDED-RESPONSE-BODY',
}}}


class Response(io.BytesIO):
    status = 200

    def read(self, size=-1):
        self.requested_size = size
        return super().read(size)


class DataProvenanceTests(unittest.TestCase):
    def setUp(self):
        guard = patch('data_provenance._HTTP.open', side_effect=AssertionError('Unexpected external HTTP'))
        self.send = guard.start()
        self.addCleanup(guard.stop)

    def fetch(self, body=None, deadline=200):
        self.send.side_effect = None
        self.response = Response(json.dumps(RECORD if body is None else body).encode())
        self.send.return_value = self.response
        with patch('data_provenance.time.monotonic', return_value=100):
            return provenance.fetch_data_provenance(provenance.DOI, deadline=deadline)

    def test_exact_public_get_has_no_credentials_or_private_payload(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'DO-NOT-SEND'}):
            result = self.fetch()
        request = self.send.call_args.args[0]
        self.assertEqual(request.full_url, provenance.API_URL)
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertIsNone(request.get_header('Authorization'))
        self.assertNotIn('DO-NOT-SEND', str(request.header_items()))
        self.assertEqual(self.send.call_args.kwargs['timeout'], 5)
        self.assertTrue(result['available'])
        self.assertEqual(result['status'], 'metadata_matched')
        self.assertEqual(result['metadata_updated_at'], RECORD['data']['attributes']['updated'])
        self.assertNotEqual(result['checked_at'], result['metadata_updated_at'])
        self.assertNotIn('UNNEEDED-RESPONSE-BODY', json.dumps(result))
        self.assertIn('does not verify measurement', result['note'])

    def test_remaining_workflow_budget_limits_request_and_expired_budget_makes_no_request(self):
        self.fetch(deadline=102)
        self.assertEqual(self.send.call_args.kwargs['timeout'], 2)
        self.send.reset_mock()
        with patch('data_provenance.time.monotonic', return_value=100):
            result = provenance.fetch_data_provenance(provenance.DOI, deadline=100)
        self.assertEqual(result['reason'], 'time_budget_exhausted')
        self.assertIsNone(result['checked_at'])
        self.send.assert_not_called()

    def test_unknown_dataset_never_selects_a_network_destination(self):
        for doi in ('10.0000/other', 'https://untrusted.invalid/private', None):
            result = provenance.fetch_data_provenance(doi, deadline=200)
            self.assertEqual(result['reason'], 'unsupported_dataset')
        self.send.assert_not_called()

    def test_both_returned_doi_identifiers_must_match(self):
        for location in ('id', 'doi'):
            record = copy.deepcopy(RECORD)
            if location == 'id':
                record['data']['id'] = '10.0000/wrong'
            else:
                record['data']['attributes']['doi'] = '10.0000/wrong'
            result = self.fetch(record)
            self.assertFalse(result['available'])
            self.assertEqual(result['reason'], 'doi_mismatch')
            self.assertIsNone(result['checked_at'])

    def test_malformed_and_unsafe_metadata_is_unavailable(self):
        malformed = [{}, {'data': []}]
        for key, value in (('titles', []), ('publicationYear', True), ('updated', 'not-a-date'),
                           ('url', 'https://www.osti.gov@untrusted.invalid/record')):
            record = copy.deepcopy(RECORD)
            record['data']['attributes'][key] = value
            malformed.append(record)
        for record in malformed:
            with self.subTest(record=record):
                result = self.fetch(record)
                self.assertEqual(result['reason'], 'invalid_response')
                self.assertFalse(result['available'])
        self.send.return_value = Response(b'not JSON; PRIVATE PROVIDER BODY')
        with patch('data_provenance.time.monotonic', return_value=100):
            result = provenance.fetch_data_provenance(provenance.DOI, deadline=200)
        self.assertEqual(result['reason'], 'invalid_response')
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_response_size_is_bounded(self):
        response = Response(b'x' * (provenance.MAX_BYTES + 20))
        self.send.side_effect = None
        self.send.return_value = response
        with patch('data_provenance.time.monotonic', return_value=100):
            result = provenance.fetch_data_provenance(provenance.DOI, deadline=200)
        self.assertEqual(response.requested_size, provenance.MAX_BYTES + 1)
        self.assertEqual(result['reason'], 'response_too_large')

    def test_http_errors_timeouts_and_redirects_do_not_echo_provider_details(self):
        failures = [(HTTPError('https://untrusted.invalid/PRIVATE', 302, 'PRIVATE', {}, None), 'redirect_refused'),
                    (HTTPError(provenance.API_URL, 429, 'PRIVATE', {}, None), 'http_error'),
                    (HTTPError(provenance.API_URL, 503, 'PRIVATE', {}, None), 'http_error'),
                    (TimeoutError('PRIVATE'), 'timeout'),
                    (URLError(TimeoutError('PRIVATE')), 'timeout'),
                    (URLError('PRIVATE'), 'connection_failed')]
        for error, reason in failures:
            with self.subTest(reason=reason):
                self.send.side_effect = error
                with patch('data_provenance.time.monotonic', return_value=100):
                    result = provenance.fetch_data_provenance(provenance.DOI, deadline=200)
                self.assertEqual(result['reason'], reason)
                self.assertFalse(result['available'])
                self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertIsNone(provenance._NoRedirect().redirect_request(None, None, 302, None, {}, 'https://untrusted.invalid'))

    def test_late_response_is_not_reported_as_checked(self):
        self.send.side_effect = None
        self.send.return_value = Response(json.dumps(RECORD).encode())
        with patch('data_provenance.time.monotonic', side_effect=[100, 100, 106]):
            result = provenance.fetch_data_provenance(provenance.DOI, deadline=200)
        self.assertEqual(result['reason'], 'timeout')
        self.assertIsNone(result['checked_at'])


class ProvenanceToolTests(unittest.TestCase):
    def setUp(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
        self.snapshot, self.assessment = smoke_assessment(cfg)
        guard = patch('data_provenance._HTTP.open', side_effect=AssertionError('Unexpected external HTTP'))
        self.send = guard.start()
        self.addCleanup(guard.stop)

    @staticmethod
    def calls(names, prefix=''):
        return {'tool_calls': [{'id': prefix + name, 'type': 'function',
                               'function': {'name': name, 'arguments': '{}'}} for name in names]}

    def test_api_is_model_requested_once_and_model_receives_cached_and_external_evidence(self):
        external = {'available': True, 'status': 'metadata_matched', 'checked_at': '2026-11-08T13:00:00+00:00',
                    'metadata_updated_at': '2026-01-29T18:43:32.000Z'}
        fetcher = Mock(return_value=external)
        captured = []
        replies = iter([self.calls(NAMES[:3]), self.calls(NAMES[3:]),
                        self.calls(['lookup_data_provenance'], 'again-'),
                        {'content': 'Next step: verify the room reading.'}])
        def model(options, messages):
            if len(captured) < 2:
                fetcher.assert_not_called()
            captured.append((options, copy.deepcopy(messages)))
            return next(replies)
        result = run({'enabled': True}, self.snapshot, self.assessment, model, provenance_fetcher=fetcher)
        fetcher.assert_called_once_with(provenance.DOI, deadline=captured[0][0]['_deadline'])
        messages = captured[-1][1]
        evidence = json.loads(next(m['content'] for m in messages if m.get('name') == 'lookup_data_provenance'))
        center = self.assessment['data_center']
        self.assertEqual(evidence['period_end'], center['period_end'])
        self.assertEqual(evidence['source_url'], center['source_url'])
        self.assertEqual(evidence['external_check'], external)
        self.assertEqual(result['provenance_check'], external)
        self.assertEqual(result['observation_timestamp'], center['latest']['timestamp'])
        self.assertNotEqual(result['observation_timestamp'], external['checked_at'])
        self.assertEqual(result['tools'], sorted(NAMES))
        self.send.assert_not_called()

    def test_default_fetcher_is_live_client_and_unavailable_metadata_remains_explicit(self):
        self.send.side_effect = URLError('PRIVATE network failure')
        model = Mock(side_effect=[self.calls(NAMES), {'content': 'Source metadata could not be checked live. Next step: verify the room reading.'}])
        result = run({'enabled': True}, self.snapshot, self.assessment, model)
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.args[0].full_url, provenance.API_URL)
        self.assertFalse(result['provenance_check']['available'])
        self.assertIsNone(result['provenance_check']['checked_at'])
        self.assertTrue(result['historical'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        evidence = json.loads(next(m['content'] for m in model.call_args.args[1] if m.get('name') == 'lookup_data_provenance'))
        self.assertEqual(evidence['retrieved_at'], self.assessment['data_center']['retrieved_at'])

    def test_disabled_or_unrequested_tool_makes_no_external_call(self):
        with self.assertRaises(NemotronError):
            run({'enabled': False}, self.snapshot, self.assessment)
        with self.assertRaises(NemotronError):
            run({'enabled': True}, self.snapshot, self.assessment, Mock(return_value={'content': 'No tools.'}))
        self.send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
