# Model card

Target: preoperative probability of at least one of seven adverse postoperative pathological features in clear cell renal cell carcinoma (OHP). Inputs: one arterial-phase CT series and Age (years), Tumorsize (cm), NEUT and LYMPH (10^9/L). Two routes use either the supplied binary tumour mask or KiTS21 automatic segmentation.

Frozen predictors: four-feature clinical L2 logistic regression; six-feature traditional-radiomic MLP; fourteen-feature habitat Extra Trees; ACC-selected ResNet34 2D epoch 36 and en5 adjacent-slice 2.5D epoch 16. Fusion is arithmetic mean of five probabilities. Classification uses p >= 0.3530539465287861. The threshold does not alter continuous probability or AUC.

The habitat KNN imputer contains the 296 x 5502 numeric training-donor feature matrix needed for identical missing-region handling. It has no patient names, identifiers, raw CT images or pathological outcome labels. It is a fitted preprocessing asset, not disposable cache. Removing it changes predictions when subregions are absent.

The package contains no study CT, DICOM, manual masks, clinical case tables or reader records. The bundled clinical template has a header only. Training and validation data are not redistributed. Empty masks or spatial mismatches request manual review rather than emit fabricated scores. The tool estimates risk for research and is not an autonomous treatment selector.

## Optional local operating settings in v1.1.0

The Local Settings tab supports a custom threshold, a local intercept update from labelled calibration data, and an assumption-dependent prevalence scenario. Defaults retain the original probability and threshold. Optional results and parameters are exported separately; original predictions, branch explanations and model weights are unchanged. See [LOCAL_SETTINGS.md](LOCAL_SETTINGS.md) for equations, assumptions, input requirements and verification scope. The original inference evaluation used v1.0.0; these optional settings have not been clinically validated in the reported cohorts.
