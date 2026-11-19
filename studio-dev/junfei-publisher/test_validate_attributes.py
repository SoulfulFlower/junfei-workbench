import json
from pathlib import Path
import subprocess
import sys
import unittest

from validate_attributes import validate_packet


def fixture():
    schema = {'$schema': 'https://schemas.amazon.com/unsupported-identification-only',
              'type': 'object', 'required': ['shirt_size'], 'additionalProperties': False,
              '$defs': {'system': {'type': 'string', 'enum': ['as1']}},
              'properties': {'shirt_size': {'type': 'array', 'minItems': 1, 'items': {
                  'type': 'object', 'required': ['size', 'size_class', 'size_system'],
                  'properties': {'size': {'type': 'string'}, 'size_class': {'enum': ['alpha', 'numeric']},
                                 'size_system': {'$ref': '#/$defs/system'}},
                  'allOf': [{'if': {'required': ['size_class'], 'properties': {'size_class': {'const': 'alpha'}}},
                             'then': {'properties': {'size': {'enum': ['s', 'm', 'l']}}}}]}}}}
    attrs = {'shirt_size': [{'size': 's', 'size_class': 'alpha', 'size_system': 'as1'}]}
    return {'schema': schema, 'records': [{'id': 'original-child', 'attributes': attrs}]}


class ValidateAttributesTests(unittest.TestCase):
    def test_local_definitions_and_conditionals_accept_real_values(self):
        packet = fixture()
        packet['records'] *= 0
        packet['records'] = [{'id': f'child-{i}', 'attributes': fixture()['records'][0]['attributes']} for i in range(31)]
        proof, code = validate_packet(packet)
        self.assertEqual(code, 0)
        self.assertEqual(proof, {'passed': True, 'checkedCount': 31, 'errors': []})

    def test_missing_required_size_metadata_is_reported_at_exact_path(self):
        packet = fixture()
        del packet['records'][0]['attributes']['shirt_size'][0]['size_system']
        proof, code = validate_packet(packet)
        self.assertEqual(code, 1)
        self.assertEqual(proof['errors'][0]['id'], 'original-child')
        self.assertEqual(proof['errors'][0]['path'], ['shirt_size', 0])
        self.assertIn('size_system', proof['errors'][0]['message'])

    def test_conditional_enum_rejects_wrong_size_without_dumping_value(self):
        packet = fixture()
        packet['records'][0]['attributes']['shirt_size'][0]['size'] = 'private-value-that-must-not-be-logged'
        proof, code = validate_packet(packet)
        self.assertEqual(code, 1)
        self.assertEqual(proof['errors'][0]['path'], ['shirt_size', 0, 'size'])
        self.assertNotIn('private-value', json.dumps(proof))

    def test_remote_reference_variants_are_rejected_before_evaluation(self):
        for keyword in ('$ref', '$dynamicRef', '$recursiveRef'):
            packet = fixture()
            packet['schema']['properties']['shirt_size'] = {keyword: 'https://example.invalid/schema'}
            proof, code = validate_packet(packet)
            self.assertEqual(code, 2)
            self.assertEqual(proof['checkedCount'], 0)
            self.assertIn('local # references', proof['errors'][0]['message'])

    def test_unresolved_local_reference_cannot_trigger_remote_lookup(self):
        packet = fixture()
        packet['schema']['properties']['shirt_size'] = {'$ref': '#/$defs/missing'}
        proof, code = validate_packet(packet)
        self.assertEqual(code, 2)
        self.assertTrue(proof['configurationError'])

    def test_malformed_schema_is_configuration_error(self):
        packet = fixture()
        packet['schema']['type'] = 'not-a-json-type'
        proof, code = validate_packet(packet)
        self.assertEqual(code, 2)
        self.assertIn('invalid', proof['errors'][0]['message'])

    def test_diagnostics_are_bounded_but_every_record_is_checked(self):
        packet = fixture()
        packet['records'] = [{'id': str(i), 'attributes': {}} for i in range(50)]
        proof, code = validate_packet(packet)
        self.assertEqual(code, 1)
        self.assertEqual(proof['checkedCount'], 50)
        self.assertEqual(len(proof['errors']), 10)
        self.assertTrue(proof['truncated'])
        self.assertTrue(all(len(error['message']) <= 240 for error in proof['errors']))

    def test_invalid_packet_and_duplicate_record_ids_fail_closed(self):
        cases = [None, {'schema': {}, 'records': []}, {'schema': {}, 'records': [{'id': 'a', 'attributes': []}]}]
        duplicate = fixture()
        duplicate['records'] *= 2
        cases.append(duplicate)
        for packet in cases:
            proof, code = validate_packet(packet)
            self.assertEqual(code, 2)
            self.assertFalse(proof['passed'])

    def test_cli_invalid_json_returns_structured_error_without_traceback(self):
        script = str(Path(__file__).with_name('validate_attributes.py'))
        result = subprocess.run([sys.executable, '-X', 'utf8', script], input='{not json', text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, '')
        self.assertFalse(json.loads(result.stdout)['passed'])

    def test_cli_missing_library_fails_with_configuration_receipt(self):
        script = str(Path(__file__).with_name('validate_attributes.py'))
        result = subprocess.run([sys.executable, '-S', '-X', 'utf8', script], input=json.dumps(fixture()), text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, '')
        self.assertIn('requires jsonschema', json.loads(result.stdout)['errors'][0]['message'])


if __name__ == '__main__':
    unittest.main()
