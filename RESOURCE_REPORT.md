# Storage and measured resources

The validation computer used 64-bit Windows, an Intel Core i9-13900HX processor, 31.7 GiB installed system RAM, and an NVIDIA GeForce RTX 4080 Laptop GPU with 12 GiB VRAM. Cases were processed sequentially.

| Route | Total elapsed seconds | Peak summed process working set (GiB) | Peak summed private commit (GiB) | Peak total GPU usage (GiB) |
|---|---:|---:|---:|---:|
| Supplied masks, 3 cases | 334.1 | 4.61 | 8.41 | 2.21 |
| Automatic mask, 1 case | 811.7 | 8.53 | 14.50 | 3.87 |

Working-set and private-memory figures are the sums across the inference process tree sampled once per second. GPU usage is the whole GPU, including other running desktop applications, rather than exclusive OHP allocation. Per-process working sets can contain shared pages, so these values are planning measurements rather than exact physical-memory accounting. Elapsed times include DICOM conversion, image processing, the selected mask route and all five OHP branches.

At report generation, the package occupied 5.996 GB (5.584 GiB), excluding generated run outputs. The original end-to-end directory occupied 11.026 GB before this package was created. Required models and frozen numerical assets are retained; unrelated R, old duplicate models, static compiler libraries and unrelated imaging/AI packages are excluded. The bundled GPU runtime accounts for much of the remaining size.

A practical provision is Windows 10/11 x64, 32 GB RAM, a compatible NVIDIA GPU with 12 GB VRAM, and at least 20 GB free working space after the program has been copied. Larger scans may need additional RAM and disk space. These recommendations are not claimed as experimentally established minimum requirements. CPU mode is available through `start_cpu.cmd`, but full-volume CPU performance was not measured in this release validation. A system CUDA toolkit, OneKey installation, system Python or R installation is not required. A compatible NVIDIA graphics driver is needed for GPU operation.

The complete release is ready to run offline. Internet access is used only by optional environment repair or source-only installation tools. Copy the entire directory, not just the executable. Keep patient inputs, analysis outputs and publication/upload destinations separate.
