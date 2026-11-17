# Local operating settings in software v1.0

The Local Settings tab is optional. Its default state uses the original probability and the original threshold, 0.3530539465287861. The frozen five-branch predictors, preprocessing, segmentation and arithmetic-mean fusion have not changed. All reported cohort and reader-study analyses use the locked default probabilities and threshold. Local-setting verification is reported separately.

## Available settings

- **Original probability:** keep the original probability. An optional custom threshold changes classification only.
- **Intercept update:** enter an independently estimated log-odds intercept, or fit one from a local CSV with columns `fusion_prob` and `OHP` (0/1). Both outcome classes are required. The fit fixes the slope at one and solves `sum(logistic(logit(p_i) + a)) = sum(y_i)`. A fit summary describes the calibration sample; it is not a held-out evaluation.
- **Prevalence scenario:** enter a local OHP prevalence in percent. The log-odds shift is `logit(local prevalence) - logit(114/296)`. The source prevalence is the development proportion, 114/296. This calculation assumes stable predictor distributions within outcome classes and appropriate source probabilities; prevalence alone cannot establish calibration in a new setting.

The configured probability is `logistic(logit(original probability) + intercept)`. Nonzero adjustments clip exact endpoint probabilities to [1e-12, 1-1e-12] for numerical calculation. The zero-offset/default path returns each original probability exactly, including zero and one. Intercept updating addresses mean risk; it does not estimate or correct a calibration slope. Local calibration and threshold choices require appropriate data and separate evaluation before clinical use.

## Files and interpretation

Apply Preview shows original and configured probabilities and classifications side by side. Export Local Results writes a new timestamped CSV, JSON parameter record and HTML report under the batch's `local_settings/` folder. The original `patient_predictions.csv`, original run manifest, weights and branch outputs are not replaced. The JSON records the source prediction-file hash, software version, threshold, adjustment mode, effective offset and any calibration-fit summary.

Overview, Branch Results, the original HTML report, branch contributions and Grad-CAM remain tied to the original model probability. Arithmetic branch contributions do not decompose the nonlinearly adjusted local probability. Restore Defaults resets the optional settings and restores the original probability and threshold.

The application includes a configurable post-processing facility. It does not claim improved calibration, diagnostic accuracy, surgical outcomes or clinical benefit for any specific external institution. Those effects need separate evaluation. The published model-performance and reader-study analyses remain based on the original predictions and threshold.

## Reproducible software checks

Run `runtime/python312/python.exe tests/test_local_settings.py`. The tests cover exact default behaviour, the threshold boundary, known log-odds calculations, finite monotonic adjustments, intercept fitting, invalid inputs, repeated exports, HTML escaping and preservation of original prediction and manifest files. No study images or patient identifiers are required.
