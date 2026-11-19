from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import ziniao_plugin as plugin


class PluginTests(unittest.TestCase):
    def header(self, labels, origin='https://sellercentral.amazon.com'):
        return {'ok':True,'data':{'data':{'exceptionDetails':None,'result':json.dumps({
            'origin':origin,'visibleHeaderCount':len(labels),'labels':labels})}}}

    def site(self, url='https://sellercentral.amazon.co.uk/myinventory/inventory?marketplaceID=UK&sort=sku'):
        return {'sellercentralConfirmed':True,'storeId':'123','sellercentralUrl':url,'sellercentralTargetId':'actual',
                'sellercentralSelection':{'method':'actual_unique_visible_header','label':'Example Store 英国',
                    'origin':'https://sellercentral.amazon.co.uk','url':url}}

    def test_cli_navigation_text_receipt_is_supported_without_fabricating_page_state(self):
        response=type('Response',(),{'returncode':0,'stdout':'✓ 页面已导航','stderr':''})()
        with patch.object(plugin.subprocess,'run',return_value=response):
            result=plugin.run('cli','page','visit','--store-id','123')
        self.assertTrue(result['ok'])
        self.assertNotIn('loginVerified',result)

    def setUp(self):
        self.options=dict(store_id='123',store_name='授权店铺',market='US',seller='Example Store',account='示例ERP账号',timeout=0)
        self.resolved={'ok':True,'data':{'matched':True,'storeId':'123','name':'授权店铺'}}
        self.page={'ok':True,'data':{'data':{'url':plugin.POPUP,'targetId':'actual',
                   'content':'站点 美国 店铺 Example Store 版本号 Chrome146 用户 示例ERP账号 退出 获取ASIN'}}}

    def test_existing_authenticated_popup_does_not_navigate_or_login_again(self):
        with patch.object(plugin,'run',side_effect=[self.resolved,self.page,self.page]) as run:
            result=plugin.open_and_verify('cli',**self.options)
        self.assertTrue(result['loginVerified'])
        self.assertIsNone(result['navigationAcknowledged'])
        self.assertFalse(result['cookiesCopied'])
        self.assertFalse(any('visit' in call.args for call in run.call_args_list))

    def test_navigation_error_is_reconciled_by_actual_authenticated_document(self):
        original={'ok':True,'data':{'url':'https://sellercentral.amazon.com/','targetId':'actual','content':'Example Store 美国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,original,{'ok':False},self.page]) as run:
            result=plugin.open_and_verify('cli',**self.options)
        self.assertTrue(result['loginVerified'])
        self.assertFalse(result['navigationAcknowledged'])
        self.assertEqual(sum('visit' in call.args for call in run.call_args_list),1)

    def test_wrong_country_or_account_never_passes(self):
        self.assertFalse(plugin.check_identity({'url':plugin.POPUP,'content':'站点 英国 店铺 Example Store 版本号 Chrome146 用户 示例ERP账号 退出'},'US','Example Store','示例ERP账号'))
        for text in ['站点 美国 店铺 其他店铺 版本号 Chrome146 用户 示例ERP账号 退出','站点 美国 店铺 Example Store 版本号 Chrome146 用户 其他账号 退出']:
            with self.assertRaises(ValueError):
                plugin.check_identity({'url':plugin.POPUP,'content':text},'US','Example Store','示例ERP账号')

    def test_login_form_is_not_a_success(self):
        self.assertFalse(plugin.check_identity({'url':plugin.POPUP,'content':'站点 美国 店铺 Example Store 请登陆获取更多功能!'},'US','Example Store','示例ERP账号'))
        self.assertFalse(plugin.check_identity({'url':plugin.POPUP,'content':'站点 店铺 版本号 加载中'},'US','Example Store','示例ERP账号'))

    def test_wrong_store_stops_before_opening_plugin(self):
        with patch.object(plugin,'run',return_value={'ok':True,'data':{'matched':True,'storeId':'999','name':'授权店铺'}}) as run:
            with self.assertRaises(ValueError):plugin.open_and_verify('cli',**self.options)
        run.assert_called_once()

    def test_site_change_checks_real_sellercentral_domain_and_country(self):
        old={'ok':True,'data':{'content':'站点 英国 店铺 Example Store 版本号 Chrome146 用户 示例ERP账号 退出','url':plugin.POPUP}}
        actual={'ok':True,'data':{'content':'菜单 Example Store 美国 良好','url':'https://sellercentral.amazon.com/amazonsell/business'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,old,{'ok':True},actual,self.header(['Example Store 美国'])]) as run,patch.object(plugin.time,'sleep'):
            result=plugin.ensure_site('cli',**{k:self.options[k] for k in ('store_id','store_name','market','seller')})
        self.assertTrue(result['sellercentralConfirmed'])
        self.assertEqual(result['sellercentralSelection']['label'],'Example Store 美国')
        self.assertEqual(sum('visit' in call.args for call in run.call_args_list),1)

    def test_email_recovery_is_submitted_once_and_success_requires_actual_seller_site(self):
        signin={'ok':True,'data':{'content':'登入','url':'https://sellercentral.amazon.com/ap/signin'}}
        actual={'ok':True,'data':{'content':'菜单 Example Store 美国','url':'https://sellercentral.amazon.com/amazonsell/business'}}
        recovery={'submitted':True,'method':'observed_form_requestSubmit','credentialsRead':False}
        with patch.object(plugin,'run',side_effect=[self.resolved,signin,actual,self.header(['Example Store 美国'])]),patch.object(plugin,'submit_saved_email_form',return_value=recovery) as submit:
            result=plugin.ensure_site('cli',**{k:self.options[k] for k in ('store_id','store_name','market','seller')})
        submit.assert_called_once()
        self.assertTrue(result['sellercentralConfirmed'])
        self.assertEqual(result['loginRecovery'],recovery)

    def test_coordinate_free_submission_does_not_claim_login_or_expose_credentials(self):
        response={'ok':True,'data':{'data':{'result':'{"submitted":true,"method":"observed_form_requestSubmit","credentialsRead":false}'}}}
        with patch.object(plugin,'run',return_value=response) as run:
            result=plugin.submit_saved_email_form('cli',store_id='123',market='US')
        self.assertTrue(result['submitted']);self.assertNotIn('loginVerified',result)
        script=run.call_args.args[-1]
        self.assertIn('input#continue[type=submit]',script)
        self.assertIn('submit.form!==form',script)
        self.assertNotIn('email.value,',script)

    def test_open_menu_body_country_does_not_override_actual_selected_market(self):
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.co.uk/amazonsell/business',
              'content':'当前 Example Store 德国 菜单可选 Example Store 英国 Example Store 美国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(['Example Store 德国'],'https://sellercentral.amazon.co.uk')]) as run:
            with self.assertRaises(plugin.SiteIdentityError) as error:
                plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',timeout=0)
        self.assertEqual(error.exception.error_type,'selected_market_mismatch')
        self.assertFalse(any('visit' in call.args or 'click' in call.args for call in run.call_args_list))

    def test_unique_visible_header_must_match_exact_normalized_label_and_origin(self):
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.co.uk/amazonsell/business','content':'Example Store 英国'}}
        for labels,origin,expected in [
            (['Example Store 英国','Example Store 英国'],'https://sellercentral.amazon.co.uk','seller_header_ambiguous'),
            (['Other 英国'],'https://sellercentral.amazon.co.uk','selected_seller_mismatch'),
            (['Example Store 英国 Other'],'https://sellercentral.amazon.co.uk','selected_market_mismatch'),
            (['Example Store 英国'],'https://sellercentral.amazon.com','seller_origin_changed'),
        ]:
            with self.subTest(labels=labels,origin=origin),patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(labels,origin)]):
                with self.assertRaises(plugin.SiteIdentityError) as error:
                    plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',timeout=0)
                self.assertEqual(error.exception.error_type,expected)
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(['  Example Store\n 英国  '],'https://sellercentral.amazon.co.uk')]):
            result=plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',timeout=0)
        self.assertEqual(result['sellercentralSelection']['label'],'Example Store 英国')

    def test_unadapted_legacy_header_never_falls_back_to_body_country(self):
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.com/','content':'菜单 Example Store 美国 良好'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header([])]) as run:
            with self.assertRaises(plugin.SiteIdentityError) as error:
                plugin.ensure_site('cli',**{k:self.options[k] for k in ('store_id','store_name','market','seller')},timeout=0)
        self.assertEqual(error.exception.error_type,'seller_header_unavailable')
        script=run.call_args.args[-1]
        self.assertIn("querySelectorAll('.dropdown-account-switcher-header')",script)
        self.assertIn("style.visibility!=='hidden'",script)
        self.assertNotIn('document.body',script)
        self.assertNotIn('__vue__',script)
        self.assertNotIn('cookie',script)

    def test_header_exec_error_is_not_identity_evidence(self):
        bad={'ok':True,'data':{'data':{'result':'not JSON','exceptionDetails':{'text':'private failure'}}}}
        with patch.object(plugin,'run',return_value=bad):
            with self.assertRaises(plugin.SiteIdentityError) as error:
                plugin.selected_seller_header('cli',store_id='123')
        self.assertEqual(error.exception.error_type,'seller_header_read_failed')

    def test_main_saves_safe_failure_receipt_before_nonzero_exit_and_never_opens_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'login-UK.json'
            argv=['--store-id','123','--store-name','授权店铺','--market','UK','--seller','Example Store',
                  '--account','示例ERP账号','--ensure-site','--receipt',str(receipt)]
            with patch.object(plugin,'native_cli',return_value='cli'), \
                    patch.object(plugin,'ensure_site',side_effect=plugin.SiteIdentityError('selected_market_mismatch')), \
                    patch.object(plugin,'open_and_verify') as open_plugin,redirect_stdout(io.StringIO()):
                code=plugin.main(argv)
            result=json.loads(receipt.read_text(encoding='utf-8'))
            self.assertEqual(code,1)
            self.assertFalse(result['loginVerified'])
            self.assertEqual(result['stage'],'sellercentral_identity')
            self.assertEqual(result['errorType'],'selected_market_mismatch')
            self.assertEqual(result['storeId'],'123')
            self.assertEqual(result['marketplace'],'UK')
            self.assertFalse(result['credentialsRead'])
            open_plugin.assert_not_called()

    def test_unexpected_error_receipt_never_copies_raw_exception_stdout_or_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'login-US.json'
            argv=['--store-id','123','--store-name','授权店铺','--market','US','--seller','Example Store',
                  '--account','示例ERP账号','--receipt',str(receipt)]
            with patch.object(plugin,'native_cli',return_value='cli'), \
                    patch.object(plugin,'open_and_verify',side_effect=RuntimeError('stdout token=PRIVATE_FIXTURE stderr cookie=PRIVATE_FIXTURE')),redirect_stdout(io.StringIO()):
                code=plugin.main(argv)
            text=receipt.read_text(encoding='utf-8');result=json.loads(text)
            self.assertEqual(code,1)
            self.assertEqual(result['stage'],'plugin_identity')
            self.assertEqual(result['errorType'],'unexpected_runtime_error')
            self.assertNotIn('PRIVATE_FIXTURE',text)
            self.assertNotIn('stdout',text)
            self.assertNotIn('stderr',text)

    def test_main_success_receipt_includes_verified_header_and_plugin_identity(self):
        site=self.site()
        popup={'loginVerified':True,'storeId':'123','marketplace':'UK','credentialsRead':False}
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'login-UK.json'
            argv=['--store-id','123','--store-name','授权店铺','--market','UK','--seller','Example Store',
                  '--account','示例ERP账号','--ensure-site','--receipt',str(receipt)]
            with patch.object(plugin,'native_cli',return_value='cli'),patch.object(plugin,'ensure_site',return_value=site), \
                    patch.object(plugin,'open_and_verify',return_value=popup),redirect_stdout(io.StringIO()):
                code=plugin.main(argv)
            result=json.loads(receipt.read_text(encoding='utf-8'))
            self.assertEqual(code,0)
            self.assertTrue(result['loginVerified'])
            self.assertEqual(result['sellercentralSelection']['label'],'Example Store 英国')

    def test_authorized_market_selection_still_requires_fresh_actual_header(self):
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.co.uk/amazonsell/business','content':'Example Store 德国 菜单英国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(['Example Store 德国'],'https://sellercentral.amazon.co.uk'),
                                                  page,self.header(['Example Store 英国'],'https://sellercentral.amazon.co.uk')]), \
                patch.object(plugin.ziniao_market,'select_observed_market',return_value={'attempted':True,'confirmed':False}) as select:
            result=plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',
                                      allow_market_dom_click=True)
        select.assert_called_once()
        self.assertTrue(result['marketSelection']['confirmed'])
        self.assertEqual(result['sellercentralSelection']['label'],'Example Store 英国')

    def test_default_same_seller_market_switch_uses_native_only_then_requires_fresh_header(self):
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.com/amazonsell/business','content':'Example Store 英国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(['Example Store 英国']),page,self.header(['Example Store 美国'])]), \
                patch.object(plugin.ziniao_market,'select_observed_market',return_value={'attempted':True,'confirmed':False}) as select:
            result=plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='US',seller='Example Store')
        select.assert_called_once();self.assertIs(select.call_args.kwargs['allow_dom_click'],False)
        self.assertTrue(result['sellercentralConfirmed']);self.assertTrue(result['marketSelection']['confirmed'])

    def test_authorization_never_allows_wrong_seller_or_replays_unknown_selection(self):
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.co.uk/amazonsell/business','content':'菜单英国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(['Other 德国'],'https://sellercentral.amazon.co.uk')]), \
                patch.object(plugin.ziniao_market,'select_observed_market') as select:
            with self.assertRaises(plugin.SiteIdentityError):
                plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',timeout=0,allow_market_dom_click=True)
        select.assert_not_called()
        with patch.object(plugin,'run',side_effect=[self.resolved,page,self.header(['Example Store 德国'],'https://sellercentral.amazon.co.uk'),
                                                  page,self.header(['Example Store 德国'],'https://sellercentral.amazon.co.uk')]), \
                patch.object(plugin.ziniao_market,'select_observed_market',return_value={'attempted':True,'resultUnknown':True}) as select, \
                patch.object(plugin.time,'monotonic',side_effect=[0,0,2]):
            with self.assertRaises(plugin.SiteIdentityError) as error:
                plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',timeout=1,allow_market_dom_click=True)
        self.assertEqual(error.exception.error_type,'market_selection_unconfirmed');select.assert_called_once()

    def test_main_passes_explicit_market_dom_permission_only_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv=['--store-id','123','--store-name','授权店铺','--market','UK','--seller','Example Store',
                  '--account','示例ERP账号','--ensure-site','--allow-market-dom-click','--receipt',str(Path(tmp)/'login.json')]
            with patch.object(plugin,'native_cli',return_value='cli'), \
                    patch.object(plugin,'ensure_site',return_value=self.site()) as site, \
                    patch.object(plugin,'open_and_verify',return_value={'loginVerified':True}),redirect_stdout(io.StringIO()):
                self.assertEqual(plugin.main(argv),0)
            self.assertTrue(site.call_args.kwargs['allow_market_dom_click'])

    def test_ensure_site_main_restores_and_rechecks_same_market_after_popup_in_order(self):
        site=self.site();selection=site['sellercentralSelection'];events=[]
        popup={'loginVerified':True,'pluginUrl':plugin.POPUP,'marketplace':'UK','sellerName':'Example Store','erpAccount':'示例ERP账号'}
        def ensure(*args,**kwargs):
            if events:self.assertEqual(kwargs['verified_site'],site)
            else:self.assertNotIn('verified_site',kwargs)
            events.append('site');self.assertEqual(kwargs['market'],'UK');return site
        def verify(*args,**kwargs):events.append('popup');return popup.copy()
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'login.json';argv=['--store-id','123','--store-name','授权店铺','--market','UK',
                '--seller','Example Store','--account','示例ERP账号','--ensure-site','--receipt',str(receipt)]
            with patch.object(plugin,'native_cli',return_value='cli'),patch.object(plugin,'ensure_site',side_effect=ensure), \
                    patch.object(plugin,'open_and_verify',side_effect=verify),redirect_stdout(io.StringIO()):
                self.assertEqual(plugin.main(argv),0)
            result=json.loads(receipt.read_text(encoding='utf-8'))
        self.assertEqual(events,['site','popup','site']);self.assertTrue(result['sellercentralRetained'])
        self.assertEqual(result['afterPluginSelection'],selection);self.assertEqual(result['pluginUrl'],plugin.POPUP)
        self.assertEqual(result['sellercentralRetainedUrl'],site['sellercentralUrl'])
        self.assertEqual(result['sellercentralRetainedTargetId'],'actual')
        self.assertTrue(result['pluginObservation']['loginVerified'])
        self.assertEqual(result['identityCheckOrder'],['sellercentral_before_plugin','plugin_popup','sellercentral_after_plugin'])

    def test_restore_failure_preserves_popup_proof_but_never_claims_final_seller_site_is_retained(self):
        site=self.site()
        popup={'loginVerified':True,'pluginUrl':plugin.POPUP,'marketplace':'UK','sellerName':'Example Store','erpAccount':'示例ERP账号'}
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'login.json';argv=['--store-id','123','--store-name','授权店铺','--market','UK',
                '--seller','Example Store','--account','示例ERP账号','--ensure-site','--receipt',str(receipt)]
            with patch.object(plugin,'native_cli',return_value='cli'), \
                    patch.object(plugin,'ensure_site',side_effect=[site,plugin.SiteIdentityError('seller_header_unavailable')]), \
                    patch.object(plugin,'open_and_verify',return_value=popup),redirect_stdout(io.StringIO()):
                self.assertEqual(plugin.main(argv),1)
            result=json.loads(receipt.read_text(encoding='utf-8'))
        self.assertFalse(result['sellercentralRetained']);self.assertFalse(result['loginVerified'])
        self.assertEqual(result['stage'],'sellercentral_retained');self.assertNotIn('afterPluginSelection',result)
        self.assertTrue(result['pluginObservation']['loginVerified']);self.assertEqual(result['pluginUrl'],plugin.POPUP)

    def test_without_ensure_site_main_keeps_legacy_popup_only_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/'login.json';argv=['--store-id','123','--store-name','授权店铺','--market','UK',
                '--seller','Example Store','--account','示例ERP账号','--receipt',str(receipt)]
            with patch.object(plugin,'native_cli',return_value='cli'),patch.object(plugin,'ensure_site') as site, \
                    patch.object(plugin,'open_and_verify',return_value={'loginVerified':True,'pluginUrl':plugin.POPUP}) as popup,redirect_stdout(io.StringIO()):
                self.assertEqual(plugin.main(argv),0)
            result=json.loads(receipt.read_text(encoding='utf-8'))
        site.assert_not_called();popup.assert_called_once();self.assertTrue(result['loginVerified'])
        self.assertNotIn('sellercentralRetained',result)

    def test_post_plugin_restores_actual_non_home_url_and_query_on_same_target(self):
        site=self.site();url=site['sellercentralUrl']
        popup={'ok':True,'data':{'url':plugin.POPUP,'targetId':'actual','content':'插件'}}
        restored={'ok':True,'data':{'url':url,'targetId':'actual','content':'Example Store 英国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,popup,{'ok':True},restored,
                self.header(['Example Store 英国'],'https://sellercentral.amazon.co.uk')]) as run:
            result=plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',verified_site=site,timeout=0)
        visits=[c.args for c in run.call_args_list if c.args[1:3]==('page','visit')]
        self.assertEqual(len(visits),1);self.assertEqual(visits[0][visits[0].index('--url')+1],url)
        self.assertNotEqual(url,plugin.SELLER_URLS['UK']);self.assertEqual(result['sellercentralUrl'],url)
        self.assertEqual(result['sellercentralTargetId'],'actual')

    def test_verified_return_url_comes_from_the_actual_selected_header_document(self):
        url=self.site()['sellercentralUrl']
        page={'ok':True,'data':{'url':'https://sellercentral.amazon.co.uk/amazonsell/business','targetId':'actual','content':'Example Store 英国'}}
        header=self.header(['Example Store 英国'],'https://sellercentral.amazon.co.uk')
        header['data']['data']['result']=json.dumps({'origin':'https://sellercentral.amazon.co.uk','url':url,
            'visibleHeaderCount':1,'labels':['Example Store 英国']})
        with patch.object(plugin,'run',side_effect=[self.resolved,page,header]):
            result=plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',timeout=0)
        self.assertEqual(result['sellercentralUrl'],url);self.assertEqual(result['sellercentralSelection']['url'],url)
        self.assertEqual(plugin.verified_site_target(result,store_id='123',market='UK',seller='Example Store'),(url,'actual'))

    def test_unverified_cross_origin_credential_or_wrong_target_return_is_rejected_without_navigation(self):
        for url in ('https://sellercentral.amazon.com/myinventory/inventory',
                    'https://sellercentral.amazon.co.uk.evil.invalid/inventory',
                    'https://user:password@sellercentral.amazon.co.uk/inventory',
                    'http://sellercentral.amazon.co.uk/inventory',
                    'https://sellercentral.amazon.co.uk/ap/signin'):
            site=self.site(url)
            with self.subTest(url=url),patch.object(plugin,'run') as run:
                with self.assertRaises(plugin.SiteIdentityError):
                    plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',verified_site=site)
                run.assert_not_called()
        for mutate in (lambda s:s.update(sellercentralConfirmed=False),lambda s:s.pop('sellercentralTargetId'),
                       lambda s:s['sellercentralSelection'].update(method='body_text'),
                       lambda s:s['sellercentralSelection'].update(label='Example Store 德国')):
            site=self.site();mutate(site)
            with patch.object(plugin,'run') as run:
                with self.assertRaises(plugin.SiteIdentityError):
                    plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',verified_site=site)
                run.assert_not_called()
        popup={'ok':True,'data':{'url':plugin.POPUP,'targetId':'different-target','content':'插件'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,popup]) as run:
            with self.assertRaises(plugin.SiteIdentityError) as error:
                plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',verified_site=self.site())
        self.assertEqual(error.exception.error_type,'seller_return_target_changed')
        self.assertFalse(any('visit' in call.args for call in run.call_args_list))

    def test_redirected_return_never_claims_original_page_even_with_valid_header(self):
        site=self.site();popup={'ok':True,'data':{'url':plugin.POPUP,'targetId':'actual','content':'插件'}}
        redirected={'ok':True,'data':{'url':plugin.SELLER_URLS['UK'],'targetId':'actual','content':'Example Store 英国'}}
        with patch.object(plugin,'run',side_effect=[self.resolved,popup,{'ok':True},redirected,
                self.header(['Example Store 英国'],'https://sellercentral.amazon.co.uk')]):
            with self.assertRaises(plugin.SiteIdentityError) as error:
                plugin.ensure_site('cli',store_id='123',store_name='授权店铺',market='UK',seller='Example Store',verified_site=site,timeout=0)
        self.assertEqual(error.exception.error_type,'seller_return_url_changed')


if __name__=='__main__':unittest.main()
