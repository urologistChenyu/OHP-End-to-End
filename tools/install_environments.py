"""Install dependencies outside the tracked source/model files. Windows x64."""
from pathlib import Path
import argparse,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]

def run(args):
    print('Installing:', ' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True)

def python_source(value,version):
    if value:return [value]
    return ['py','-'+version] if os.name=='nt' else ['python'+version]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--python39');p.add_argument('--python312');p.add_argument('--cpu',action='store_true')
    p.add_argument('--only',choices=['radiomics','inference','both'],default='both')
    a=p.parse_args()
    for kind,ver in [('radiomics','3.9'),('inference','3.12')]:
        if a.only not in ['both',kind]:continue
        env=ROOT/('.venv39' if kind=='radiomics' else '.venv312')
        py=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if not py.is_file():
            run(python_source(a.python39 if kind=='radiomics' else a.python312,ver)+['-m','venv',str(env)])
        run([py,'-m','pip','install','--upgrade','pip'])
        if kind=='inference':
            index='https://download.pytorch.org/whl/'+('cpu' if a.cpu else 'cu128')
            run([py,'-m','pip','install','-r',ROOT/'environment/requirements-torch.txt','--index-url',index])
        run([py,'-m','pip','install','-r',ROOT/('environment/requirements-'+kind+'.txt')])
    if a.only=='both':run([ROOT/'.venv312'/('Scripts/python.exe' if os.name=='nt' else 'bin/python'),ROOT/'tools/check_install.py'])
    print('Environment preparation completed. Run start_windows.cmd or launch.py.',flush=True)
if __name__=='__main__':main()
