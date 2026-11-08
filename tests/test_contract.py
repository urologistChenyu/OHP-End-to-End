"""Data-free model contract and relocation tests."""
from pathlib import Path
import unittest,json,ast,hashlib
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_relative_manifest(self):
        z=json.loads((ROOT/'configs/model_manifest.json').read_text(encoding='utf-8'))
        for key in ['radiomics_yaml','clinical_model','traditional_model','habitat_model','weight2d','weight25d','segmentation_source','segmentation_model_root']:
            self.assertFalse(Path(z[key]).is_absolute());self.assertTrue((ROOT/z[key]).exists())
    def test_model_fingerprints(self):
        for z in json.loads((ROOT/'ASSET_MANIFEST.json').read_text(encoding='utf-8'))['model_files']:
            self.assertEqual(hashlib.sha256((ROOT/z['file']).read_bytes()).hexdigest(),z['sha256'])
    def test_no_private_paths_or_onekey_import(self):
        for p in ROOT.rglob('*.py'):
            if any(x.startswith('.venv') for x in p.parts) or 'runtime' in p.relative_to(ROOT).parts or 'outputs' in p.relative_to(ROOT).parts:continue
            s=p.read_text(encoding='utf-8-sig');tree=ast.parse(s)
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):self.assertFalse(any(n.name.startswith('onekey') for n in node.names))
                if isinstance(node,ast.ImportFrom):self.assertFalse((node.module or '').startswith('onekey'))
            if p.resolve()!=Path(__file__).resolve():
                self.assertNotIn('G:'+ '/'+'codex-ohp',s);self.assertNotIn('G:'+ '\\'+'codex-ohp',s)
    def test_header_only_clinical_template(self):
        self.assertEqual((ROOT/'examples/clinical_template.csv').read_text().strip(),'ID,Age,Tumorsize,NEUT,LYMPH')
    def test_current_workpoint(self):
        import sys;sys.path.insert(0,str(ROOT))
        from run_ohp_publication import THRESHOLD,FIELDS
        self.assertEqual(THRESHOLD,0.3530539465287861);self.assertEqual(FIELDS,['Age','Tumorsize','NEUT','LYMPH'])
if __name__=='__main__':unittest.main()
