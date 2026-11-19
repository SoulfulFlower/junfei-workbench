"""Select the observed Seller Central market UI with trusted input first.

Only ordinary document controls are read/clicked. No account state, cookies,
credentials, private framework objects or marketplace endpoints are accessed.
DOM clicks require the separately supplied explicit permission.
"""
import json
import subprocess
import time

MARKETS = {'US': ('美国', 'US', 'https://sellercentral.amazon.com'),
           'UK': ('英国', 'GB', 'https://sellercentral.amazon.co.uk')}


class MarketSelectionError(ValueError):
    def __init__(self, reason):
        self.error_type = 'market_selection_' + reason
        super().__init__('实际市场菜单未通过唯一目标、安全可点击或同店铺核验，未继续切站')


# Kept self-contained so tests execute this exact production browser script.
MARKET_CLICK_SCRIPT = r'''(() => {
 const cfg=__MARKET_CONFIG__;
 const fail=reason=>JSON.stringify({ok:false,stage:'guard',reason});
 const norm=value=>String(value||'').trim().replace(/\s+/g,' ');
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&!e.closest('[aria-hidden="true"]');};
 const enabled=e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true'&&!e.closest('[inert]');
 const hit=e=>{e.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});const r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
   if(x<0||y<0||x>=innerWidth||y>=innerHeight)return false;const top=document.elementFromPoint(x,y);return !!top&&(top===e||e.contains(top));};
 if(location.origin!==cfg.origin)return fail('origin_changed');
 if(document.querySelector('input[type="password"]'))return fail('authentication_required');
 const roots=[...document.querySelectorAll('.dropdown-account-switcher.account-switcher-root')].filter(visible);
 const headers=[...document.querySelectorAll('.dropdown-account-switcher-header')].filter(visible);
 if(roots.length!==1||headers.length!==1||!roots[0].contains(headers[0]))return fail('ambiguous_header');
 const root=roots[0],header=headers[0],label=norm(header.innerText||header.textContent),expected=norm(cfg.seller+' '+cfg.country);
 const globalLabels=header.querySelectorAll('.dropdown-account-switcher-header-label-global');
 if(globalLabels.length!==1||norm(globalLabels[0].innerText||globalLabels[0].textContent)!==cfg.seller)return fail('seller_mismatch');
 if(header.getAttribute('role')!=='button'||!enabled(header))return fail('header_disabled');
 if(label===expected)return JSON.stringify({ok:true,stage:'already_selected',clicked:false,label});
 if(!label.startsWith(cfg.seller+' '))return fail('seller_mismatch');
 const expanded=header.getAttribute('aria-expanded');
 if(!['true','false'].includes(expanded))return fail('header_changed');
 if(expanded==='false'){
   if(!hit(header))return fail('obscured');
   const selector='.dropdown-account-switcher-header';
   if(document.querySelectorAll(selector).length!==1)return fail('ambiguous_header');
   if(cfg.action==='open'){header.click();return JSON.stringify({ok:true,stage:'menu_open_requested',clicked:true,method:'user_authorized_DOM_click'});}
   return JSON.stringify({ok:true,stage:'menu_closed',clicked:false,selector});
 }
 if(cfg.action==='open')return JSON.stringify({ok:true,stage:'already_open',clicked:false});
 const selector='.dropdown-account-switcher.account-switcher-root .dropdown-account-switcher-list-item[title="'+cfg.country+'"]';
 const candidates=[...root.querySelectorAll('.dropdown-account-switcher-list-item')].filter(e=>visible(e)&&norm(e.getAttribute('title'))===cfg.country);
 if(candidates.length!==1)return fail('ambiguous_market');
 const row=candidates[0];
 if(!row.classList.contains('dropdown-account-switcher-list-item-indented')||norm(row.innerText||row.textContent)!==cfg.country||!enabled(row))return fail('market_disabled_or_changed');
 const flags=row.querySelectorAll('img[data-test="country-flag-'+cfg.flag+'"]');
 if(flags.length!==1)return fail('flag_mismatch');
 let owner=row.previousElementSibling;
 while(owner&&owner.classList.contains('dropdown-account-switcher-list-item')&&owner.classList.contains('dropdown-account-switcher-list-item-indented'))owner=owner.previousElementSibling;
 if(!owner||!owner.classList.contains('dropdown-account-switcher-list-item')||owner.classList.contains('dropdown-account-switcher-list-item-indented')||
    norm(owner.getAttribute('title'))!==cfg.seller||norm(owner.innerText||owner.textContent)!==cfg.seller||!visible(owner))return fail('seller_mismatch');
 const matches=document.querySelectorAll(selector);
 if(matches.length!==1||matches[0]!==row)return fail('ambiguous_market');
 if(!hit(row))return fail('obscured');
 if(cfg.action==='click'){row.click();return JSON.stringify({ok:true,stage:'market_click_requested',clicked:true,method:'user_authorized_DOM_click'});}
 return JSON.stringify({ok:true,stage:'ready',clicked:false,selector});
})()'''


def _exec(run, cli, store_id, config, action):
    script = MARKET_CLICK_SCRIPT.replace('__MARKET_CONFIG__', json.dumps({**config, 'action': action}, ensure_ascii=False))
    value = run(cli, 'page', 'exec', '--store-id', store_id, '--script', script)
    if not isinstance(value, dict) or value.get('ok') is not True:
        raise MarketSelectionError('read_unconfirmed')
    while isinstance(value, dict):
        if value.get('ok') is False:
            raise MarketSelectionError('read_unconfirmed')
        if isinstance(value.get('data'), dict):
            value = value['data']
        else:
            break
    try:
        if value.get('exceptionDetails'):
            raise ValueError('execution failed')
        result = json.loads(value.get('result', ''))
        if not isinstance(result, dict) or type(result.get('ok')) is not bool or not isinstance(result.get('stage'), str):
            raise ValueError('invalid result')
    except (ValueError, TypeError, AttributeError):
        raise MarketSelectionError('read_unconfirmed') from None
    if not result['ok']:
        reasons = {'origin_changed', 'authentication_required', 'ambiguous_header', 'seller_mismatch',
                   'header_disabled', 'header_changed', 'obscured', 'ambiguous_market',
                   'market_disabled_or_changed', 'flag_mismatch'}
        raise MarketSelectionError(result.get('reason') if result.get('reason') in reasons else 'read_unconfirmed')
    return result


def _geometry_unavailable(value):
    """Only an explicit known pre-dispatch input failure permits DOM fallback."""
    if not isinstance(value, dict):
        return False
    if value.get('ok') is False:
        error = value.get('error')
        if isinstance(error, dict) and 'coordinate input geometry is unavailable' in str(error.get('message', '')):
            return True
    return isinstance(value.get('data'), dict) and _geometry_unavailable(value['data'])


def _acknowledged(value):
    if not isinstance(value, dict) or value.get('ok') is not True:
        return False
    while isinstance(value.get('data'), dict):
        value = value['data']
        if value.get('ok') is False:
            return False
    return True


def select_observed_market(run, cli, *, store_id, market, seller, deadline, allow_dom_click=False):
    """Attempt each UI control once; caller must verify fresh selected identity."""
    country, flag, origin = MARKETS[market]
    config = {'seller': seller, 'country': country, 'flag': flag, 'origin': origin}
    outcome = {'attempted': False, 'confirmed': False, 'targetLabel': seller + ' ' + country,
               'method': 'ziniao_cli_trusted_click', 'credentialsRead': False}
    state = _exec(run, cli, store_id, config, 'inspect')
    if state['stage'] == 'already_selected':
        return {**outcome, 'alreadySelected': True}

    def click_once(state, action):
        if time.monotonic() >= deadline:
            raise MarketSelectionError('deadline')
        outcome['attempted'] = True
        try:
            response = run(cli, 'page', 'click', '--store-id', store_id, '--selector', state['selector'],
                           '--timeout', str(max(1, min(5000, int((deadline - time.monotonic()) * 1000)))))
        except (ValueError, subprocess.TimeoutExpired):
            outcome.update(resultUnknown=True, reason='native_result_unknown')
            return False
        if _geometry_unavailable(response):
            # Geometry errors are pre-dispatch failures. Reinspect before the
            # explicitly authorized DOM fallback; never fallback on unknowns.
            fresh = _exec(run, cli, store_id, config, 'inspect')
            if fresh['stage'] == 'already_selected' or (action == 'open' and fresh['stage'] == 'ready'):
                return True
            if not allow_dom_click:
                outcome.update(nativeInputUnavailable=True, resultUnknown=True, reason='native_input_unavailable')
                return False
            required = 'menu_closed' if action == 'open' else 'ready'
            if fresh['stage'] != required:
                outcome.update(resultUnknown=True, reason='page_changed_after_native_failure')
                return False
            outcome.update(method='user_authorized_DOM_click', nativeInputUnavailable=True)
            try:
                result = _exec(run, cli, store_id, config, action)
            except (ValueError, subprocess.TimeoutExpired):
                outcome.update(resultUnknown=True, reason='dom_result_unknown')
                return False
            return result.get('clicked') is True or result['stage'] in ('already_open', 'already_selected')
        if not _acknowledged(response):
            outcome.update(resultUnknown=True, reason='native_result_unknown')
            return False
        return True

    if state['stage'] == 'menu_closed':
        if not click_once(state, 'open'):
            return outcome
        # Read only while the menu renders, under the original site deadline.
        menu_deadline = min(deadline, time.monotonic() + 2)
        while True:
            state = _exec(run, cli, store_id, config, 'inspect')
            if state['stage'] != 'menu_closed' or time.monotonic() >= menu_deadline:
                break
            time.sleep(min(0.2, max(0, menu_deadline - time.monotonic())))
    if state['stage'] == 'already_selected':
        return outcome
    if state['stage'] != 'ready':
        return {**outcome, 'resultUnknown': True, 'reason': 'menu_open_unconfirmed'}
    click_once(state, 'click')
    return outcome
