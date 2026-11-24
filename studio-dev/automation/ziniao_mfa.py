"""Submit the OTP already filled by Ziniao without exporting its value."""
import json
import time


def inspect(run, cli, store_id, origin):
    script = r'''(() => {
      if(location.origin!==ORIGIN)return JSON.stringify({state:'origin_changed'});
      if(location.pathname!=='/ap/mfa')return JSON.stringify({state:'left_mfa'});
      const fields=[...document.querySelectorAll('#auth-mfa-otpcode')];
      const buttons=[...document.querySelectorAll('#auth-signin-button')];
      const visible=e=>e.getBoundingClientRect().width>0&&getComputedStyle(e).visibility!=='hidden';
      if(fields.length!==1||buttons.length!==1||!visible(fields[0])||!visible(buttons[0]))
        return JSON.stringify({state:'form_changed'});
      const error=[...document.querySelectorAll('.a-alert-error')].filter(visible).length>0;
      return JSON.stringify({state:error?'code_rejected':/^\d{6}$/.test(fields[0].value)&&!buttons[0].disabled?'ready':'waiting_autofill'});
    })()'''.replace('ORIGIN', json.dumps(origin))
    value = run(cli, 'page', 'exec', '--store-id', store_id, '--script', script)
    if value.get('ok') is not True:
        raise ValueError('二步验证页面检查失败')
    while isinstance(value.get('data'), dict):
        value = value['data']
    result = json.loads(value.get('result', '{}'))
    if result.get('state') not in {'origin_changed', 'left_mfa', 'form_changed', 'code_rejected', 'ready', 'waiting_autofill'}:
        raise ValueError('二步验证页面格式发生变化')
    return result['state']


def submit_autofilled(run, cli, *, store_id, origin, deadline):
    """One bounded submission. A failed/expired code goes to the desktop helper."""
    while time.monotonic() < deadline:
        state = inspect(run, cli, store_id, origin)
        if state == 'left_mfa':
            return {'status': 'left_mfa', 'submitted': False, 'otpRecorded': False}
        if state in {'origin_changed', 'form_changed'}:
            raise ValueError('二步验证页面或站点发生变化')
        if state == 'code_rejected':
            return {'status': 'refresh_required', 'submitted': False, 'otpRecorded': False}
        if state == 'ready':
            try:
                run(cli, 'page', 'click', '--store-id', store_id, '--selector', '#auth-signin-button',
                    '--timeout', '5000')
            except (ValueError, TimeoutError):
                pass  # Read the same page before deciding whether it was submitted.
            while time.monotonic() < deadline:
                state = inspect(run, cli, store_id, origin)
                if state == 'left_mfa':
                    return {'status': 'left_mfa', 'submitted': True, 'otpRecorded': False}
                if state in {'code_rejected', 'ready'}:
                    return {'status': 'refresh_required', 'submitted': True, 'otpRecorded': False}
                time.sleep(0.25)
            return {'status': 'submission_unconfirmed', 'submitted': None, 'otpRecorded': False}
        time.sleep(0.25)
    return {'status': 'autofill_pending', 'submitted': False, 'otpRecorded': False}
