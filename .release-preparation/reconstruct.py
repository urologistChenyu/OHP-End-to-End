from pathlib import Path
from zipfile import ZipFile
import json,base64,hashlib,urllib.request,subprocess,os
root=Path('release_build');root.mkdir(exist_ok=True)
with ZipFile('.release-preparation/recipe.zip') as z:parts=json.loads(z.read('recipe.json'))
urls={'DOWNLOAD_INSTRUCTIONS.txt': 'https://github.com/urologistChenyu/OHP-End-to-End/releases/download/v1.0.0/DOWNLOAD_INSTRUCTIONS.txt', 'OHP_End_to_End_Windows_part01_of03.zip': 'https://github.com/urologistChenyu/OHP-End-to-End/releases/download/v1.0.0/OHP_End_to_End_Windows_part01_of03.zip', 'OHP_End_to_End_Windows_part02_of03.zip': 'https://github.com/urologistChenyu/OHP-End-to-End/releases/download/v1.0.0/OHP_End_to_End_Windows_part02_of03.zip', 'OHP_End_to_End_Windows_part03_of03.zip': 'https://github.com/urologistChenyu/OHP-End-to-End/releases/download/v1.0.0/OHP_End_to_End_Windows_part03_of03.zip', 'SHA256SUMS.txt': 'https://github.com/urologistChenyu/OHP-End-to-End/releases/download/v1.0.0/SHA256SUMS.txt'}
for p in parts:
    old=root/(p['name']+'.source')
    urllib.request.urlretrieve(urls[p['name']],old)
    out=root/p['name']
    with old.open('rb') as fi,out.open('wb') as fo:
        for op in p['ops']:
            if op[0]=='insert':fo.write(base64.b64decode(op[1]));continue
            _,start,length=op;fi.seek(start)
            while length:
                b=fi.read(min(length,8*1024*1024));assert b;fo.write(b);length-=len(b)
    assert hashlib.file_digest(out.open('rb'),'sha256').hexdigest()==p['sha256']
    with ZipFile(out) as z:assert z.testzip() is None
    subprocess.run(['gh','release','upload','v1.0',str(out),'--clobber','--repo',os.environ['GITHUB_REPOSITORY']],check=True)
    print('RECONSTRUCTED_HASH_CRC_AND_UPLOAD_VERIFIED',p['name'],flush=True)
    old.unlink();out.unlink()
for name in ['SHA256SUMS.txt','DOWNLOAD_INSTRUCTIONS.txt']:
    subprocess.run(['gh','release','upload','v1.0','.release-preparation/'+name,'--clobber','--repo',os.environ['GITHUB_REPOSITORY']],check=True)
