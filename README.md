# OHP End-to-End Analysis

## Download the complete Windows application

**Use the [v1.0.0 release downloads](https://github.com/urologistChenyu/OHP-End-to-End/releases/tag/v1.0.0) for the ready-to-run application.** Download all three OHP_End_to_End_Windows_partNN_of03.zip files and extract each into the same destination. Together they create one complete 02_End_to_End folder. Open 02_End_to_End/OHP.exe after all three archives have been extracted. Windows can extract these ordinary ZIP files without another archive program.

The complete download contains both Python environments, the trained models and processing libraries. No OneKey installation or system Python is required. Use 64-bit Windows 10/11; hardware and NVIDIA-driver requirements are in USER_MANUAL_EN.md. Keep the complete application folder together.

## Model and input routes

The application estimates the preoperative probability of a binary composite of seven adverse pathological features in clear cell renal cell carcinoma. Risk is the mean of clinical, conventional-radiomic, habitat, 2D ResNet34 and adjacent-slice 2.5D ResNet34 probabilities. Each branch has weight 0.2; positive classification uses probability >= 0.3530539465287861.

Input one arterial-phase CT/DICOM series and Age (years), Tumorsize (cm, CT diameter), NEUT and LYMPH (10^9/L). Choose automatic KiTS21 segmentation or supply a spatially matched reviewed binary tumour mask. Both routes use the same downstream predictors. Processing produces the CT-mask display, five branch estimates, final risk, classification and an exported report. Choose a separate output directory for patient processing.

## Source code and final trained assets

This Code view contains the inference implementation, desktop source, fixed configurations and setup documentation. The complete runtime and binary assets are distributed in the release downloads, rather than the GitHub-generated source-code archive. The final model files, features, preprocessing and anonymous cohort predictions are documented in [OHP Paper Data and Models](https://github.com/urologistChenyu/OHP-Paper-Data-Models). Source-only users can prepare the pinned environments under environment/ and retrieve the matching trained assets before inference. The full Windows release already includes them.

The code is provided under the existing OHP source licence; pretrained segmentation assets and bundled third-party software retain their respective licences and attributions. See LICENSE, THIRD_PARTY_NOTICES.md and licenses/.

Related platform: [OHP Reader Study](https://github.com/urologistChenyu/OHP-Reader-Study-Platform). Version: v1.0.0.
