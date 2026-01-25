## GGUF CLIP 加载器 (多模态/LTX)

智能 CLIP 加载器，支持自动识别并加载 1 到 4 个 CLIP 模型。支持 **LTX Video (双CLIP)**、SD3 (三CLIP) 和 SDXL 等架构。

### ⚙️ 属性参数

| 参数名 | 说明 |
| :--- | :--- |
| **clip_path_1** | **(必须)** 主要 CLIP 模型（如 T5 XXL GGUF）。 |
| **clip_path_2** | (可选) 第二个 CLIP 模型（如 CLIP ViT-L）。LTX Video 或 SDXL 需要此项。 |
| **clip_path_3** | (可选) 第三个 CLIP 模型（SD3 需要）。 |
| **clip_path_4** | (可选) 第四个 CLIP 模型。 |
| **clip_type** | **架构类型**。告诉系统如何组装 CLIP。<br>• `sd3`: 适用于 **SD3** 和 **LTX Video** (推荐)。<br>• `stable_diffusion`: 适用于 SD1.5/SDXL。<br>• `flux`: 适用于 Flux 模型。<br>• `ltxv`: 专用于 LTX Video (如果内核支持)。 |

### 🚀 LTX Video 配置示例
*   **clip_path_1**: 选择 `t5xxl_fp16.gguf` (或 Q8_0.gguf)
*   **clip_path_2**: 选择对应的 ViT 模型 (如果需要)
*   **clip_type**: 选择 `sd3` (因为 LTX 使用 T5 架构，与 SD3 兼容性最好)