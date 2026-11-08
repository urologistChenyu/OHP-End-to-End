from pathlib import Path
import json,sys,subprocess,hashlib,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from package_paths import load_config

def main():
    cfg=load_config();result={'models':[],'environments':[]}
    for row in json.loads((ROOT/'ASSET_MANIFEST.json').read_text(encoding='utf-8'))['model_files']:
        p=ROOT/row['file']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('Asset checksum differs: '+row['file'])
        result['models'].append(row['file'])
    for key,modules in [('python39',['numpy','pandas','scipy','sklearn','joblib','radiomics','SimpleITK','skimage','pywt','trimesh']),
                        ('python312',['numpy','pandas','SimpleITK','pydicom','PIL','torch','torchvision','nnunet','batchgenerators','tkinter','matplotlib','skimage','matplotlib.backends.backend_tkagg','mpl_toolkits.mplot3d'])]:
        interpreter=Path(cfg[key])
        if not interpreter.is_file():raise RuntimeError('Interpreter missing: '+str(interpreter)+'; run tools/install_environments.py')
        code='import importlib,json,sys;names='+repr(modules)+';mods=[importlib.import_module(n) for n in names];print(json.dumps({"python":sys.version.split()[0],"prefix":sys.prefix,"modules":{n:getattr(m,"__version__","installed") for n,m in zip(names,mods)},"module_paths":{n:getattr(m,"__file__",None) for n,m in zip(names,mods)},"onekey_loaded":any(n.startswith("onekey") for n in sys.modules)}))'
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
        env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
        r=subprocess.run([str(interpreter),'-B','-s','-c',code],text=True,capture_output=True,encoding='utf-8',errors='replace',env=env)
        if r.returncode:raise RuntimeError(key+' import check failed:\n'+r.stderr)
        result['environments'].append(json.loads(r.stdout.strip().splitlines()[-1]))
    from run_ohp_publication import check_assets
    check_assets()
    result['status']='PASS';result['selected_device']=cfg['image_device'];result['cpu_fallback_available']=True
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
