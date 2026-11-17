"""Install or restore the optional-settings update beside an existing OHP release."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,tempfile
from datetime import datetime
ROOT=Path(__file__).resolve().parent
if ROOT.name=="tools":ROOT=ROOT.parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inside(rel):
 p=(ROOT/rel).resolve()
 try:p.relative_to(ROOT)
 except ValueError:raise ValueError('Update path is outside the application folder.') from None
 return p

def replace_file(source,dest):
 dest.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(dir=dest.parent,prefix='.ohp-update-',delete=False) as stream:
  temp=Path(stream.name);stream.write(source.read_bytes())
 os.replace(temp,dest)

def restore(folder):
 folder=Path(folder).resolve();folder.relative_to(ROOT/'updates_backup')
 state=json.loads((folder/'restore.json').read_text(encoding='utf-8'))
 for rel,old in state.items():
  dest=inside(rel)
  if old is None:
   if dest.exists():dest.unlink()
  else:
   source=folder/'files'/rel
   if digest(source)!=old:raise ValueError('Backup integrity check failed: '+rel)
   replace_file(source,dest)
 print('Previous source files restored. Model assets and saved predictions were not modified.')

def install():
 payload=ROOT/'local_settings_update_payload'
 manifest=json.loads((payload/'UPDATE_MANIFEST.json').read_text(encoding='utf-8'))
 if not (ROOT/'ohp_gui.py').is_file() or not (ROOT/'configs/model_manifest.json').is_file():raise ValueError('Extract the update into the existing complete OHP application folder first.')
 contract=json.loads((ROOT/'ASSET_MANIFEST.json').read_text(encoding='utf-8'))
 if contract.get('protocol')!='OHP_mean5_ACC_20261104':raise ValueError('This update requires the matching frozen OHP release.')
 for rel,expected in manifest['files'].items():
  inside(rel)
  if digest(payload/rel)!=expected:raise ValueError('Update integrity check failed: '+rel)
 backup=ROOT/'updates_backup'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');backup.mkdir(parents=True)
 state={}
 for rel in manifest['files']:
  dest=inside(rel);state[rel]=digest(dest) if dest.exists() else None
  if dest.exists():
   copy=backup/'files'/rel;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,copy)
 (backup/'restore.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
 try:
  for rel in manifest['files']:replace_file(payload/rel,inside(rel))
  for rel,expected in manifest['files'].items():
   if digest(inside(rel))!=expected:raise RuntimeError('Installed file integrity check failed: '+rel)
 except Exception:
  restore(backup);raise
 print('OHP v1.1.0 optional local settings installed.')
 print('Previous source files:',backup)
 print('Frozen models, runtime, default inference and saved predictions are unchanged.')

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restore');parser.add_argument('--restore-latest',action='store_true');args=parser.parse_args()
 if args.restore:restore(args.restore)
 elif args.restore_latest:
  backups=sorted((ROOT/'updates_backup').glob('*/restore.json'))
  if not backups:raise ValueError('No previous source backup was found.')
  restore(backups[-1].parent)
 else:install()
