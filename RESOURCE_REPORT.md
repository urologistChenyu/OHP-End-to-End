# Operating requirements

Use Windows 10 or Windows 11, 64-bit. A practical configuration is 32 GB system RAM, an NVIDIA GPU with 12 GB VRAM, and at least 20 GB free working space after extracting the complete software. Larger CT volumes may require additional memory and disk space. CPU mode is available through start_cpu.cmd and can take substantially longer.

The complete Windows release includes its Python runtimes, inference libraries and trained model assets. A system Python, R, CUDA toolkit or proprietary platform installation is not required. GPU operation requires a compatible NVIDIA graphics driver. Internet access is used only for optional environment repair or source-only installation.

Keep the complete 02_End_to_End folder together and open OHP.exe. Keep the complete application folder together. Choose a separate writable output directory and retain adequate working space for DICOM conversion, masks, extracted features and reports. Source patient CT files remain in the selected input location.
