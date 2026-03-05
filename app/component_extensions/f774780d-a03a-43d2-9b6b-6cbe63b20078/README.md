# ComfyUI-GGUF
GGUF Quantization support for native ComfyUI models

This is currently very much WIP. These custom nodes provide support for model files stored in the GGUF format popularized by [llama.cpp](https://github.com/ggerganov/llama.cpp).

While quantization wasn't feasible for regular UNET models (conv2d), transformer/DiT models such as flux seem less affected by quantization. This allows running it in much lower bits per weight variable bitrate quants on low-end GPUs. For further VRAM savings, a node to load a quantized version of the T5 text encoder is also included.

![Comfy_Flux1_dev_Q4_0_GGUF_1024](https://github.com/user-attachments/assets/70d16d97-c522-4ef4-9435-633f128644c8)

Note: The "Force/Set CLIP Device" is **NOT** part of this node pack. Do not install it if you only have one GPU. Do not set it to cuda:0 then complain about OOM errors if you do not undestand what it is for. There is not need to copy the workflow above, just use your own workflow and replace the stock "Load Diffusion Model" with the "Unet Loader (GGUF)" node.

## Installation

> [!IMPORTANT]  
> Make sure your ComfyUI is on a recent-enough version to support custom ops when loading the UNET-only.

---

### 中文安装指南

#### 前置要求

- ComfyUI 最新版本（需要支持自定义 ops）
- Python 环境
- GGUF 依赖库

#### 安装步骤

**方法一：常规安装（推荐）**

将仓库克隆到 ComfyUI 的 custom_nodes 文件夹中：

```bash
git clone https://github.com/city96/ComfyUI-GGUF
```

安装依赖：

```bash
pip install --upgrade gguf
```

**方法二：Windows 便携版安装**

1. 进入 `ComfyUI_windows_portable` 文件夹（包含 `run_nvidia_gpu.bat` 的目录）
2. 执行以下命令：

```bash
git clone https://github.com/city96/ComfyUI-GGUF ComfyUI/custom_nodes/ComfyUI-GGUF
.\python_embeded\python.exe -s -m pip install -r .\ComfyUI\custom_nodes\ComfyUI-GGUF\requirements.txt
```

**方法三：ComfyUI-Manager 安装**

1. 打开 ComfyUI-Manager
2. 点击 "Install Custom Nodes"
3. 搜索 "ComfyUI-GGUF"
4. 点击安装

#### 模型放置

将 `.gguf` 模型文件放入以下目录：

```
ComfyUI/models/unet/
```

---

#### 注意事项

⚠️ **不要**在只有一块 GPU 的情况下使用 "Force/Set CLIP Device" 功能，否则可能导致 OOM 错误。

⚠️ MacOS Sequoia 系统需要使用 torch 2.4.1 版本，2.6.X 夜间版本会导致 "M1 buffer is not large enough" 错误。

---

## Usage

Simply use the GGUF Unet loader found under the `bootleg` category. Place the .gguf model files in your `ComfyUI/models/unet` folder.

LoRA loading is experimental but it should work with just the built-in LoRA loader node(s).

Pre-quantized models:

- [flux1-dev GGUF](https://huggingface.co/city96/FLUX.1-dev-gguf)
- [flux1-schnell GGUF](https://huggingface.co/city96/FLUX.1-schnell-gguf)
- [stable-diffusion-3.5-large GGUF](https://huggingface.co/city96/stable-diffusion-3.5-large-gguf)
- [stable-diffusion-3.5-large-turbo GGUF](https://huggingface.co/city96/stable-diffusion-3.5-large-turbo-gguf)

Initial support for quantizing T5 has also been added recently, these can be used using the various `*CLIPLoader (gguf)` nodes which can be used inplace of the regular ones. For the CLIP model, use whatever model you were using before for CLIP. The loader can handle both types of files - `gguf` and regular `safetensors`/`bin`.

- [t5_v1.1-xxl GGUF](https://huggingface.co/city96/t5-v1_1-xxl-encoder-gguf)

See the instructions in the [tools](https://github.com/city96/ComfyUI-GGUF/tree/main/tools) folder for how to create your own quants.
