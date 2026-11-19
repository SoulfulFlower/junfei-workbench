"""Bounded, offline standard JSON Schema validation for native draft attributes.

Amazon-specific vocabulary and the remote service's business rules are not an
approval by this validator. References are local-only; this process never
retrieves a schema or any other resource from a network.
"""
import json
import sys

MAX_ERRORS = 10
MAX_MESSAGE = 240


class ConfigurationError(ValueError):
    pass


def _local_references_only(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('$ref', '$dynamicRef', '$recursiveRef'):
                if not isinstance(child, str) or not child.startswith('#'):
                    raise ConfigurationError('Schema references must be local # references')
            _local_references_only(child)
    elif isinstance(value, list):
        for child in value:
            _local_references_only(child)


def _error_message(error):
    # jsonschema's default enum/anyOf messages can print the entire schema and
    # instance. Keep diagnostics useful without copying source data into logs.
    rule = error.validator
    if rule == 'required':
        missing = [key for key in error.validator_value if key not in error.instance]
        return ('Missing required property: ' + ', '.join(missing))[:MAX_MESSAGE]
    if rule == 'type':
        return ('Expected JSON type: ' + str(error.validator_value))[:MAX_MESSAGE]
    if rule in ('enum', 'const'):
        return 'Value does not match the schema ' + rule
    if rule in ('anyOf', 'oneOf', 'allOf', 'not', 'contains', 'additionalProperties', 'unevaluatedProperties'):
        return 'Value does not satisfy schema rule: ' + rule
    return ('Value does not satisfy schema rule: ' + str(rule))[:MAX_MESSAGE]


def _configuration_result(message):
    return {'passed': False, 'checkedCount': 0, 'configurationError': True,
            'errors': [{'id': None, 'path': [], 'schemaPath': [], 'message': str(message)[:MAX_MESSAGE]}]}


def validate_packet(packet):
    """Return (proof, exit_code), without logging instances or schema values."""
    try:
        if not isinstance(packet, dict) or set(packet) != {'schema', 'records'}:
            raise ConfigurationError('Expected only schema and records')
        schema, records = packet['schema'], packet['records']
        if not isinstance(schema, (dict, bool)):
            raise ConfigurationError('Schema must be an object or boolean')
        if not isinstance(records, list) or not records:
            raise ConfigurationError('At least one attribute record is required')
        seen = set()
        for row in records:
            if (not isinstance(row, dict) or set(row) != {'id', 'attributes'}
                    or isinstance(row.get('id'), bool) or not isinstance(row.get('id'), (str, int))
                    or not str(row['id']) or not isinstance(row.get('attributes'), dict)):
                raise ConfigurationError('Every record requires an id and attributes object')
            identity = str(row['id'])
            if identity in seen:
                raise ConfigurationError('Record ids must be unique')
            seen.add(identity)
        _local_references_only(schema)
        try:
            from jsonschema import Draft202012Validator
            from jsonschema.exceptions import SchemaError
            from referencing import Registry
            from referencing.exceptions import NoSuchResource
        except ImportError:
            raise ConfigurationError('The configured Python runtime requires jsonschema') from None

        def deny_retrieval(uri):
            raise NoSuchResource(ref=uri)

        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            raise ConfigurationError('The supplied standard JSON Schema is invalid') from None
        validator = Draft202012Validator(schema, registry=Registry(retrieve=deny_retrieval))
        errors, failed, truncated = [], False, False
        for row in records:
            for error in validator.iter_errors(row['attributes']):
                failed = True
                if len(errors) >= MAX_ERRORS:
                    truncated = True
                    # Still check the other records once, without enumerating
                    # every failing branch after the diagnostic budget is full.
                    break
                errors.append({'id': str(row['id']), 'path': list(error.absolute_path),
                               'schemaPath': list(error.absolute_schema_path), 'message': _error_message(error)})
        result = {'passed': not failed, 'checkedCount': len(records), 'errors': errors}
        if truncated:
            result['truncated'] = True
        return result, 1 if failed else 0
    except ConfigurationError as error:
        return _configuration_result(error), 2
    except Exception:
        # Unresolved references and validator failures cannot authorize a Save.
        # Do not echo a remote URI or a possibly large failing instance.
        return _configuration_result('Schema evaluation could not complete with local references'), 2


def main():
    try:
        packet = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        result, code = _configuration_result('Input is not valid JSON'), 2
    else:
        result, code = validate_packet(packet)
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(',', ':'))
    sys.stdout.write('\n')
    return code


if __name__ == '__main__':
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
