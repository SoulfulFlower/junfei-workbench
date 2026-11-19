"""Use this invocation's complete browser error before historical receipt errors."""
import json

MARKER = '__JUNFEI_EGO_APPLICATION_ERROR__'


def current_browser_error(stdout, stderr, binding, script_sha256):
    for output in (stdout, stderr):
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        for line in (output or '').splitlines():
            if not line.startswith(MARKER):
                continue
            try:
                value = json.loads(line[len(MARKER):])
            except (TypeError, ValueError):
                continue
            if (isinstance(value, dict) and type(value.get('version')) is int
                    and value['version'] == 1 and value.get('kind') == 'application_job_error'
                    and value.get('binding') == binding
                    and value.get('scriptSha256') == script_sha256
                    and isinstance(value.get('message'), str) and value['message']
                    and isinstance(value.get('stack'), str)):
                return value['message'][:1500]
    return None
