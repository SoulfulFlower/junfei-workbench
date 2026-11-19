"""Prepare office-only HTTPS listener. Uses cryptography in .deploy-venv."""
import argparse
import datetime as dt
import ipaddress
import json
import socket
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

def prepare(address, port=18767):
    ip=ipaddress.ip_address(address)
    if not ip.is_private or ip.is_loopback:
        raise ValueError('请使用办公室局域网IPv4地址')
    root=Path(__file__).parent/'data';tls=root/'tls';tls.mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(dt.timezone.utc)
    if (tls/'server.pem').exists():
        cert=x509.load_pem_x509_certificate((tls/'server.pem').read_bytes())
        san=cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if ip not in san.get_values_for_type(x509.IPAddress):
            raise ValueError('现有证书不包含该IP，请维护人员续签证书，不会覆盖旧证书')
    else:
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Junfei Office Listing Local CA')])
        ca=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=3650)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,key_cert_sign=True,crl_sign=True,content_commitment=False,data_encipherment=False,key_agreement=False,encipher_only=False,decipher_only=False),critical=True).sign(ca_key,hashes.SHA256())
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Junfei Listing Office Server')])
        cert=x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=365)).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip),x509.DNSName(socket.gethostname())]),critical=False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(ca_key,hashes.SHA256())
        (tls/'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (tls/'server-key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        (tls/'office-ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
        (root/'junfei-office-ca.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
        # No CA signing key is retained: this local CA cannot later issue other certificates.
    config={'enabled':True,'address':address,'port':port,'url':f'https://{address}:{port}','certificateExpires':cert.not_valid_after_utc.isoformat()}
    (root/'deployment.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(config,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--address',required=True);parser.add_argument('--port',type=int,default=18767)
    args=parser.parse_args();prepare(args.address,args.port)
