"""Explicit installation of the pinned automatic-clothing model (no image upload)."""
import hashlib,json,urllib.request
from pathlib import Path


def install(model='cloth-parser'):
    if model not in ('cloth-parser','human-parser'):raise ValueError('Unknown automatic clothing model')
    folder=Path(__file__).parent/'models'/model
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
    path=folder/manifest['file'];expected=manifest['sha256']
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:return path
    temporary=path.with_suffix('.download')
    try:
        with urllib.request.urlopen(manifest['url'],timeout=60) as response,temporary.open('wb') as output:
            while chunk:=response.read(1024*1024):output.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=expected:raise ValueError('Automatic clothing model SHA256 differs from its manifest')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return path


if __name__=='__main__':
    for model in ('cloth-parser','human-parser'):print(install(model))
