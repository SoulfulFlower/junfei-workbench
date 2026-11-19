import app_paths
"""Windows DPAPI locally; Fernet with a separately managed key on Linux."""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

ROOT = app_paths.DATA / 'credentials'
WINDOWS = os.name == 'nt'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(payload, decrypt=False):
    if not WINDOWS:
        from cryptography.fernet import Fernet, InvalidToken
        key_path = os.environ.get('JUNFEI_MASTER_KEY_FILE')
        if not key_path:
            raise ValueError('服务器尚未配置密钥加密文件，请联系管理员')
        cipher = Fernet(Path(key_path).read_bytes().strip())
        try:
            return cipher.decrypt(payload) if decrypt else cipher.encrypt(payload)
        except InvalidToken as error:
            raise ValueError('服务器密钥文件与加密资料不匹配') from error
    buffer = ctypes.create_string_buffer(payload)
    source = Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Windows 密钥加密或解密失败')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def location(name):
    if name not in ('deepseek', 'apimart', 'sellersprite', 'aigocode', 'openai_image'):
        raise ValueError('未知密钥服务')
    root = Path(os.environ.get('JUNFEI_SHARED_CREDENTIALS', str(ROOT))) if name == 'sellersprite' else ROOT
    return root / (name + ('.dpapi' if WINDOWS else '.fernet'))


def save(name, value):
    path = location(name)
    if not value:
        path.unlink(missing_ok=True)
        return
    encrypted = crypt(value.encode('utf-8'))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    if not WINDOWS:
        temporary.chmod(0o600)
    temporary.replace(path)


def load(name):
    path = location(name)
    if not path.exists():
        return ''
    try:
        return crypt(path.read_bytes(), decrypt=True).decode('utf-8')
    except (ValueError, UnicodeError, OSError):
        # Do not expose credentials or silently overwrite an unreadable file.
        return ''
