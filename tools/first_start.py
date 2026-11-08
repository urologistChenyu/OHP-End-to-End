"""Double-click bootstrap using bundled Python cores; no system Python required."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time,hashlib
ROOT=Path(__file__).resolve().parents[1]
ENV=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
ENV.pop('PYTHONHOME',None);ENV.pop('PYTHONPATH',None)

def run(args):
    subprocess.run(list(map(str,args)),check=True,cwd=ROOT,env=ENV)

def ready(py,modules):
    code='import importlib;[importlib.import_module(n) for n in '+repr(modules)+']'
    return subprocess.run([str(py),'-B','-s','-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=ENV).returncode==0

def main():
    p=argparse.ArgumentParser();p.add_argument('--cpu',action='store_true');p.add_argument('--install-only',action='store_true');a=p.parse_args()
    py39=ROOT/'runtime/python39/python.exe';py312=ROOT/'runtime/python312/python.exe'
    if not py39.is_file() or not py312.is_file():raise FileNotFoundError('Portable Python core is missing. Copy the complete upload directory.')
    phases=[('radiomics',py39,['numpy','pandas','radiomics','sklearn','scipy','SimpleITK','skimage','pywt','trimesh']),
            ('inference',py312,['numpy','pandas','torch','torchvision','nnunet','SimpleITK','pydicom','PIL','tkinter','batchgenerators','matplotlib','skimage','matplotlib.backends.backend_tkagg','mpl_toolkits.mplot3d'])]
    logdir=ROOT/'outputs/setup';logdir.mkdir(parents=True,exist_ok=True)
    for kind,py,modules in phases:
        if ready(py,modules):
            print(kind+': installed',flush=True);continue
        print('First use: installing '+kind+' dependencies. Internet is required during this step.',flush=True)
        run([py,'-B','-s','-m','ensurepip','--upgrade'])
        run([py,'-B','-s','-m','pip','install','--upgrade','pip'])
        if kind=='inference':
            try:gpu=subprocess.run(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],capture_output=True,timeout=10).returncode==0
            except (OSError,subprocess.TimeoutExpired):gpu=False
            cpu=a.cpu or not gpu
            run([py,'-B','-s','-m','pip','install','--no-compile','-r',ROOT/'environment/requirements-torch.txt','--index-url','https://download.pytorch.org/whl/'+('cpu' if cpu else 'cu128')])
        run([py,'-B','-s','-m','pip','install','--no-compile','-r',ROOT/('environment/requirements-'+kind+'.txt')])
        if not ready(py,modules):raise RuntimeError(kind+' dependencies did not pass import checks')
    run([py312,'-B','-s',ROOT/'tools/check_install.py'])
    (logdir/'installation_complete.json').write_text(json.dumps({'completed_at':time.strftime('%Y-%m-%d %H:%M:%S'),'runtime':'bundled cores; local site-packages','no_system_python_required':True}),encoding='utf-8')
    if not a.install_only:run([py312,'-B','-s',ROOT/'launch.py'])
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('\nSetup/start failed: '+str(e)+'\nCheck the Internet connection and free disk space, then start again.',flush=True)
        raise
