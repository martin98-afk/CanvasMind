### 组件说明

1.  **输入参数 (`vae_name`)**:
    *   **普通 VAE**: 直接输入文件名，例如 `ae.safetensors` 或 `sdxl_vae.pt`（必须位于 `ComfyUI/models/vae/` 下）。
    *   **TAESD (Tiny AutoEncoder)**: 输入以下关键词之一（无需文件后缀，但需确保文件存在于 `ComfyUI/models/vae_approx/`）：
        *   `taesd`: 适用于 SD1.5
        *   `taesdxl`: 适用于 SDXL
        *   `taesd3`: 适用于 Stable Diffusion 3
        *   `taef1`: 适用于 Flux.1
    *   **Pixel Space**: 输入 `pixel_space`，用于不需要 VAE 压缩/解压的场景。

2.  **核心逻辑**:
    *   我保留了原代码中 `load_taesd` 的逻辑，特别是对 `taef1` (Flux) 和 `taesd3` 的支持。这意味着通过此组件，你可以加载 Flux 的微型 VAE 进行极速预览。
    *   使用了 `folder_paths.get_full_path_or_raise`，这保证了路径搜索逻辑与 ComfyUI 原生完全一致。

3.  **依赖**:
    *   需要 `comfyui` 环境（依赖 `folder_paths`, `comfy.utils`, `comfy.sd`）。