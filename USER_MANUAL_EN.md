# OHP End-to-End Analysis — User Manual

## 1. What to open

Copy the **entire release folder** to a writable local drive on a 64-bit Windows computer. Keep the internal files and directories together. Double-click **`OHP.exe`**. For visible startup diagnostics, use **`start_windows.cmd`**. Neither launcher requires Python to be installed system-wide. The release includes two isolated CPython cores and the inference libraries used by the application.

The desktop interface is in English. The automatic-mask and supplied-mask routes use the same five frozen OHP predictors and the same fusion rule. Installation-repair tools are included under `tools/`; they are not part of routine patient processing.

## 2. Computer requirements

Use Windows 10 or Windows 11, 64-bit. A practical planning configuration is **32 GB system RAM**, an **NVIDIA GPU with 12 GB VRAM**, and **at least 20 GB free working space after copying the software**. Larger CT volumes can require more memory and working space. Operating requirements and offline installation details are provided in `RESOURCE_REPORT.md`.

An NVIDIA driver compatible with the packaged CUDA 12.8 PyTorch runtime is needed for GPU acceleration. The installed CUDA toolkit is not required. If CUDA is unavailable, the application can select CPU inference; automatic full-volume segmentation can then be considerably slower. The complete release runs locally without an Internet connection. Internet access is needed only if dependencies are being repaired or reinstalled.

## 3. Input data

Provide one intended arterial-phase contrast-enhanced CT series per patient. Select **all DICOM data files of that series**, not one representative slice. Do not combine different phases, reconstructions or series from one patient. Alternatively, use an identified CT volume directory supported by the application.

Four clinical variables are required for each case:

| CSV field | Meaning | Unit |
|---|---|---|
| `ID` | Case identifier matching the CT and, when used, the mask | Text |
| `Age` | Age | Years |
| `Tumorsize` | Tumour diameter | cm |
| `NEUT` | Neutrophil count | 10⁹/L |
| `LYMPH` | Lymphocyte count | 10⁹/L |

The included `examples/clinical_template.csv` contains a header only. Supply your own case rows. Empty fields, duplicate identifiers, invalid units and nonnumeric values must be resolved before a result is produced.

## 4. Choose the mask route

**Automatic route:** select automatic segmentation. The bundled KiTS21 nnU-Net model generates a tumour mask before OHP feature extraction. Review the CT–mask overlay after segmentation.

**Supplied-mask route:** select supplied mask and choose the directory of reviewed binary tumour masks. Each mask must match its case identifier and represent tumour with label 1 and background with label 0. A kidney-plus-tumour multiclass segmentation must first be converted to a binary tumour mask. The program aligns masks in physical coordinates using nearest-neighbour interpolation and checks whether the aligned mask is nonempty.

An empty or spatially incompatible mask produces a review message rather than a fabricated OHP probability. Correct or delineate the tumour mask and rerun through the supplied-mask route. The two routes share the prediction algorithm; changing the contour can change the prediction.

## 5. Run a case or batch

1. Open the launcher. In the case workspace, select DICOM files or a CT case directory.
2. Discover the cases. Confirm that each identifier corresponds to the intended series.
3. Enter the four clinical variables or import a CSV with the exact column names above.
4. Choose automatic or supplied-mask input. For the latter, select the matching mask directory.
5. Select a **new, writable output directory**. Avoid overwriting an existing completed run.
6. Start analysis. Cases are processed sequentially to control memory use. Pause other large imaging or GPU tasks if memory is limited.
7. Inspect **CT & Mask**. Review the tumour extent in axial, coronal and sagittal views and in the available 3D display.
8. Inspect **Branch Results** and the final risk. Save the output directory for traceability.

A single case can be scored. AUC, sensitivity, specificity and other cohort-level diagnostic metrics require a collection of cases with reference outcomes; they are not properties of a single uploaded patient.

## 6. Interpret the outputs

The five branch probabilities are clinical, traditional radiomic, habitat radiomic, 2D CNN and 2.5D CNN. Fusion is:

`p(OHP) = (p_clinical + p_traditional + p_habitat + p_2D + p_2.5D) / 5`

The displayed OHP percentage is `100 × p(OHP)`. The current classification rule is **positive when p ≥ 0.3530539465287861**, and negative otherwise. The threshold changes classification, not the continuous probability or ROC AUC.

OHP denotes at least one of seven adverse postoperative pathological features: WHO/ISUP grade 3–4, tumour necrosis, lymphovascular invasion, renal sinus invasion, perinephric fat invasion, sarcomatoid differentiation or rhabdoid differentiation. The probability is a preoperative risk estimate; definitive OHP assessment uses postoperative pathology. Review the result with the clinical and imaging findings. The software does not prescribe an operation or treatment.

## 7. Saved files and reopening a run

| File or directory | Contents |
|---|---|
| `patient_predictions.csv` | Successful cases, five branch probabilities, fused probability, OHP percentage and classification |
| `case_status.csv` | Status and review messages for all submitted cases |
| `run_manifest.json` | Model protocol, weights, threshold, asset hashes, input route and elapsed time |
| `segmentation_progress.json` | Segmentation status used by the interface |
| `cases/` | Case-level converted images, masks, extracted features and processing logs |
| `OHP_result_report.html` | Summary report generated by the interface after loading results |

Use **Open completed batch** to restore an existing run with its `run_manifest.json`. The interface verifies the stored model protocol and fusion rule. It reads the saved probabilities instead of silently rerunning or altering them.

## 8. Common problems

**No window appears:** run `start_windows.cmd` from an extracted, writable folder. Do not run the program inside a ZIP viewer. A console error is retained when startup fails. Avoid moving only the launcher without its runtime and model directories.

**A dependency is missing:** run `runtime/python312/python.exe tools/first_start.py --install-only`. This repair step uses the Internet and writes dependencies inside the release folder. The normal ready-to-run release does not require this step.

**CUDA is unavailable:** update the NVIDIA driver or launch `start_cpu.cmd` to select CPU mode. Advanced users can set the environment variable `OHP_DEVICE=cpu`. There is no requirement to install OneKey, a CUDA toolkit, R, or the original research directory.

**Not enough memory:** close other large applications, process one case at a time, and use an adequately provisioned computer. Volume size influences memory more than the number of completed rows in the results table.

**Empty mask or wrong tumour extent:** review the correct CT phase and source geometry, provide a corrected binary tumour mask, and use the supplied-mask route.

**DICOM series cannot be assembled:** select one complete CT series with distinct, ordered slice positions. Mixed series and irregular slice spacing require review.

**Clinical IDs do not match:** align the CSV identifier with the identified CT case and the supplied-mask filename. Do not infer the relationship from file order.

**Chinese or other non-ASCII image paths fail:** set `OHP_WORK_DIR` to a writable ASCII path with sufficient free space. The application stages medical-image I/O there. This does not require renaming or moving the original CT archive.

## 9. Command-line use

From the release folder:

```powershell
runtime/python312/python.exe run_ohp.py --input YOUR_CT_DIRECTORY --clinical YOUR_CLINICAL.csv --mask-dir YOUR_MASK_DIRECTORY --output YOUR_NEW_OUTPUT_DIRECTORY
```

Omit `--mask-dir` for automatic segmentation. Selected DICOM files can be provided through a JSON input manifest containing `cases`, each with `ID` and `dicom_files`. Use the GUI to construct the input when unsure about series membership.

Advanced settings: `OHP_PYTHON312`, `OHP_PYTHON39`, `OHP_WORK_DIR` and `OHP_DEVICE`. Ordinary users do not need to change the two interpreter paths.

## 10. Reproducibility and redistribution

The branch weights, selected features, normalisation parameters, three habitat intensity centres and KNN imputation state are frozen. The habitat imputer is a necessary fitted numerical asset; removing it changes missing-region handling. Raw study CT, DICOM, clinical case tables, patient masks and reader-study responses are not part of this release.

The source code is provided with an MIT license. Bundled KiTS21 pretrained weights retain CC BY 4.0 attribution. Bundled Python and inference dependencies retain their respective licenses. See `LICENSE`, `THIRD_PARTY_NOTICES.md`, `licenses/` and the distribution license records in the runtime directories.

Large binary models and the optional ready-to-run runtime should be distributed through a release archive or an appropriate research-data repository. Do not commit the 250 MB segmentation checkpoint as an ordinary Git object. Preserve the version and checksum manifests when redistributing a validated release.
