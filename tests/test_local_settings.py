"""Data-free numerical and file-integrity checks for optional local settings."""
import csv
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_risk_settings import LocalSettings, DEFAULT_THRESHOLD, DEVELOPMENT_PREVALENCE, fit_intercept, local_rows, export_local_settings, calibration_csv


class LocalSettingsTests(unittest.TestCase):
    def test_default_is_exact_identity(self):
        s=LocalSettings()
        for p in [0.,1e-12,0.1,DEFAULT_THRESHOLD,0.5,0.99,1.]:self.assertEqual(s.adjust(p),p)
    def test_threshold_boundary_and_custom_threshold(self):
        rows=[{'patient_id':'A','fusion_prob':DEFAULT_THRESHOLD,'pred_primary':1}]
        self.assertEqual(local_rows(rows,LocalSettings())[0]['configured_pred'],1)
        out=local_rows(rows,LocalSettings(threshold=0.5))[0]
        self.assertEqual(out['raw_probability'],out['configured_probability']);self.assertEqual(out['raw_pred_default'],1);self.assertEqual(out['configured_pred'],0)
    def test_intercept_known_odds(self):
        self.assertAlmostEqual(LocalSettings(mode='intercept',intercept=math.log(2)).adjust(0.2),1/3,14)
    def test_prevalence_equal_is_identity(self):
        s=LocalSettings(mode='prevalence',local_prevalence=DEVELOPMENT_PREVALENCE)
        self.assertEqual(s.offset,0);self.assertEqual(s.adjust(.333),.333)
    def test_prevalence_maps_source_baseline(self):
        for target in [.1,.25,.8]:self.assertAlmostEqual(LocalSettings(mode='prevalence',local_prevalence=target).adjust(DEVELOPMENT_PREVALENCE),target,14)
    def test_monotone_finite_adjustment(self):
        vals=[LocalSettings(mode='intercept',intercept=-.47).adjust(x/1000) for x in range(1001)]
        self.assertTrue(all(a<b for a,b in zip(vals,vals[1:])))
    def test_fit_known_constant_probability(self):
        fitted=fit_intercept([.8]*10,[1,1,0,0,0,0,0,0,0,0])
        self.assertAlmostEqual(fitted['intercept'],2*math.log(.25),12)
        self.assertAlmostEqual(fitted['mean_adjusted_probability'],.2,14)
    def test_fit_does_not_change_input(self):
        ps=[.1,.3,.7,.9];ys=[0,1,0,1];old=(list(ps),list(ys));fit_intercept(ps,ys);self.assertEqual((ps,ys),old)
    def test_fit_requires_both_outcomes(self):
        for y in ([0,0],[1,1],[0,2],[0,float('nan')]):
            with self.assertRaises(ValueError):fit_intercept([.2,.7],y)
    def test_invalid_settings(self):
        for kw in [dict(mode='bad'),dict(threshold=0),dict(threshold=1),dict(threshold=float('nan')),dict(mode='prevalence',local_prevalence=1),dict(mode='prevalence',local_prevalence=None),dict(intercept=float('inf'))]:
            with self.assertRaises(ValueError):LocalSettings(**kw)
    def test_invalid_probabilities_and_ids(self):
        for rows in [[{'patient_id':'A','fusion_prob':1.1}],[{'patient_id':'A','fusion_prob':float('nan')}],[{'patient_id':'','fusion_prob':.2}],[{'patient_id':'A','fusion_prob':.2}]*2,[{'patient_id':'A','fusion_prob':.2,'pred_primary':1}]]:
            with self.assertRaises(ValueError):local_rows(rows,LocalSettings())
    def test_export_keeps_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'patient_predictions.csv';source.write_text('patient_id,fusion_prob,pred_primary\nA,0.2,0\nB,0.8,1\n',encoding='utf-8')
            manifest=root/'run_manifest.json';manifest.write_text('{"original":true}');before={p.name:p.read_bytes() for p in [source,manifest]}
            result=export_local_settings(root,LocalSettings(mode='intercept',intercept=-.2))
            self.assertTrue(all((root/name).read_bytes()==blob for name,blob in before.items()));self.assertEqual(result['cases'],2)
            self.assertTrue(all(Path(result[k]).exists() for k in ['csv','json','html']))
            second=export_local_settings(root,LocalSettings());self.assertNotEqual(result['csv'],second['csv'])
    def test_calibration_csv_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'cal.csv';p.write_text('patient_id,fusion_prob,OHP\nA,0.2,0\nB,0.8,1\n')
            fit=calibration_csv(p);self.assertEqual(fit['n'],2);self.assertEqual(len(fit['source_sha256']),64)
            p.write_text('patient_id,fusion_prob,OHP\nA,0.2,0\nA,0.8,1\n')
            with self.assertRaises(ValueError):calibration_csv(p)
    def test_html_escapes_case_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'patient_predictions.csv';p.write_text('patient_id,fusion_prob,pred_primary\n<script>alert(1)</script>,0.2,0\n')
            result=export_local_settings(tmp,LocalSettings());text=Path(result['html']).read_text()
            self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)

if __name__=='__main__':unittest.main()
