# ComfyUI HAIGC Qwen3TTS

[English](README_EN.md)

ComfyUI 自定义节点，集成 Qwen3-TTS（通义千问语音合成）模型，支持声音设计、声音克隆和自定义声音生成。

## 作者

- 微信号：HAIGC1994

## 原开源项目

[https://github.com/QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)

## 功能特性

- 🎤 **声音设计 (Voice Design)**: 基于文本提示词生成自定义声音
- 🎭 **声音克隆 (Voice Clone)**: 基于参考音频克隆声音
- 🎨 **自定义声音 (Custom Voice)**: 使用预设说话人或自定义提示词生成语音
- 🌍 **多语言支持**: 支持中文、英文、日文、韩文、德文、法文、俄文、葡萄牙文、西班牙文、意大利文
- ⚡ **GPU/CPU 支持**: 支持 CUDA 加速和 CPU 运行
- 🎯 **精度控制**: 支持 FP16 和 FP32 精度

## 安装

### 1. 安装依赖

安装 Qwen3-TTS 所需的核心依赖：

```bash
pip install torch torchaudio transformers librosa soundfile accelerate
```

**注意**: 如果您的环境中已安装这些依赖，可以跳过此步骤。本插件的 `requirements.txt` 可能包含其他可选依赖。

### 2. 下载模型

将 Qwen3-TTS 模型下载到以下目录：

模型下载地址：[https://huggingface.co/collections/Qwen/qwen3-tts](https://huggingface.co/collections/Qwen/qwen3-tts)

本地存放模型路径：`ComfyUI\models\qwen-tts`

```
ComfyUI/models/qwen-tts/{model_folder_name}/
```

**支持的模型：**
- `Qwen3-TTS-12Hz-1.7B-VoiceDesign` - 支持声音设计
- `Qwen3-TTS-12Hz-1.7B-CustomVoice` - 支持自定义声音
- `Qwen3-TTS-12Hz-1.7B-Base` - 支持声音克隆
- `Qwen3-TTS-12Hz-0.6B-CustomVoice` - 轻量版自定义声音
- `Qwen3-TTS-12Hz-0.6B-Base` - 轻量版基础模型
- `Qwen3-TTS-Tokenizer-12Hz` - 分词器模型

**模型文件夹命名规则：**
- 从 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` 提取为 `Qwen3-TTS-12Hz-1.7B-VoiceDesign`
- 确保文件夹名称与模型名称的后缀部分一致

**示例目录结构：**
```
ComfyUI/
└── models/
    └── qwen-tts/
        ├── Qwen3-TTS-12Hz-1.7B-VoiceDesign/
        ├── Qwen3-TTS-12Hz-1.7B-CustomVoice/
        └── Qwen3-TTS-12Hz-1.7B-Base/
```

## 节点说明

### 1. Qwen3 TTS 模型加载

加载 Qwen3-TTS 模型到内存。

**输入参数：**
- `模型名称`: 选择要加载的模型
- `运行设备`: cuda / cpu / auto（自动选择）
- `精度`: fp16 / fp32

**输出：**
- `模型`: 加载的模型对象，用于后续的语音生成节点

**注意：** 
- 模型必须已存在于 `ComfyUI/models/qwen-tts/` 目录中，本插件不提供自动下载功能
- 模型路径固定为 `ComfyUI/models/qwen-tts/`，不支持自定义路径
- 模型加载时会自动检查本地文件，不会尝试从网络下载

### 2. Qwen3 TTS 声音设计

基于文本提示词生成自定义声音的语音。

**输入参数：**
- `模型`: 从模型加载节点获取
- `文本`: 要合成的文本内容
- `提示词`: 声音描述提示词（如："A young female voice, energetic and bright."）
- `语言` (可选): 自动 / 中文 / 英文 / 日文 / 韩文等
- `自动卸载模型` (可选): 生成后是否卸载模型以释放显存
- `最大生成Token数` (可选): 限制生成的最大长度，默认 2048
- `随机种子` (可选): 生成随机性控制
- `生成后控制` (可选): 固定 / 增加 / 减少 / 随机

**输出：**
- `音频`: 生成的音频对象（AUDIO 类型）

**模型要求：** 需要加载带有 "VoiceDesign" 的模型。

### 3. Qwen3 TTS 声音克隆

基于参考音频克隆声音并生成语音。

**输入参数：**
- `模型`: 从模型加载节点获取
- `文本`: 要合成的文本内容
- `参考音频`: 参考音频对象（AUDIO 类型）
- `参考文本` (可选): 参考音频对应的文本内容
- `语言` (可选): 自动 / 中文 / 英文 / 日文 / 韩文等
- `自动卸载模型` (可选): 生成后是否卸载模型以释放显存
- `最大生成Token数` (可选): 限制生成的最大长度，默认 2048
- `随机种子` (可选): 生成随机性控制
- `生成后控制` (可选): 固定 / 增加 / 减少 / 随机

**输出：**
- `音频`: 生成的音频对象（AUDIO 类型）

**模型要求：** 需要加载带有 "Base" 的模型。

### 4. Qwen3 TTS 自定义声音

使用预设说话人或自定义提示词生成语音。

**输入参数：**
- `模型`: 从模型加载节点获取
- `文本`: 要合成的文本内容
- `预设说话人`: 选择预设说话人（Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee）
- `语言` (可选): 自动 / 中文 / 英文 / 日文 / 韩文等
- `提示词` (可选): 自定义声音描述，会覆盖预设说话人的默认提示词
- `自动卸载模型` (可选): 生成后是否卸载模型以释放显存
- `最大生成Token数` (可选): 限制生成的最大长度，默认 2048
- `随机种子` (可选): 生成随机性控制
- `生成后控制` (可选): 固定 / 增加 / 减少 / 随机

**预设说话人：**
- `Vivian`: 明亮、略带锋芒的年轻女声
- `Serena`: 温暖、温柔的年轻女声
- `Uncle_Fu`: 成熟、低沉的男声
- `Dylan`: 年轻、清晰的北京男声
- `Eric`: 活泼、略带沙哑的成都男声
- `Ryan`: 充满活力的男声，节奏感强
- `Aiden`: 阳光、清晰的美国男声
- `Ono_Anna`: 活泼、轻快的日本女声
- `Sohee`: 温暖、情感丰富的韩国女声

**输出：**
- `音频`: 生成的音频对象（AUDIO 类型）

**模型要求：** 需要加载带有 "CustomVoice" 的模型。

## 使用示例

### 声音设计示例

```
1. Qwen3 TTS 模型加载
   - 模型名称: Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign
   - 运行设备: cuda
   - 精度: fp16

2. Qwen3 TTS 声音设计
   - 模型: [连接模型加载节点]
   - 文本: "Hello, this is a test of voice design."
   - 提示词: "A young female voice, energetic and bright."
   - 语言: 自动
```

### 声音克隆示例

```
1. Qwen3 TTS 模型加载
   - 模型名称: Qwen/Qwen3-TTS-12Hz-1.7B-Base
   - 运行设备: cuda
   - 精度: fp16

2. Qwen3 TTS 声音克隆
   - 模型: [连接模型加载节点]
   - 文本: "Hello, I am cloning this voice."
   - 参考音频: [连接音频输入节点]
   - 参考文本: "This is the reference audio text."
   - 语言: 自动
```

### 自定义声音示例

```
1. Qwen3 TTS 模型加载
   - 模型名称: Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
   - 运行设备: cuda
   - 精度: fp16

2. Qwen3 TTS 自定义声音
   - 模型: [连接模型加载节点]
   - 文本: "Hello, this is a custom voice."
   - 预设说话人: Vivian
   - 语言: 自动
```

## 注意事项

1. **模型路径**: 确保模型已下载到 `ComfyUI/models/qwen-tts/` 目录，文件夹名称必须与模型名称的后缀部分一致。

2. **模型选择**: 
   - 声音设计功能需要 "VoiceDesign" 模型
   - 声音克隆功能需要 "Base" 模型
   - 自定义声音功能需要 "CustomVoice" 模型

3. **显存管理**: 如果显存不足，可以启用"自动卸载模型"选项，生成完成后会自动将模型卸载到 CPU。

4. **语言设置**: 设置为"自动"时，模型会自动检测文本语言。

5. **音频输出**: 所有节点输出的音频对象可以通过 ComfyUI 的标准音频保存节点进行保存。

## 故障排除

### 模型未找到错误

如果出现 `模型未找到` 错误，请检查：
- 模型是否已下载到 `ComfyUI/models/qwen-tts/` 目录
- 文件夹名称是否正确（应与模型名称的后缀部分一致）
- 文件夹路径是否正确

### 功能不支持错误

如果出现功能不支持的错误，请检查：
- 加载的模型类型是否与使用的功能匹配
- VoiceDesign 功能需要 VoiceDesign 模型
- Voice Clone 功能需要 Base 模型
- Custom Voice 功能需要 CustomVoice 模型

## 许可证

请参考原项目许可证。

## 更新日志

### v1.2.0
- 新增随机种子与生成后控制选项，提升生成多样性
- 优化自定义声音提示词优先级处理

### v1.1.0
- 重命名内部包为 `_qwen_tts_haigc`，避免与系统安装的 qwen_tts 包冲突
- 修复 transformers 4.57.1 兼容性问题（check_model_inputs 装饰器）
- 优化导入逻辑，增强错误处理
- 禁用所有模型下载功能，强制使用本地文件
- 优化模型路径处理，使用 ComfyUI 标准路径管理

### v1.0.0
- 初始版本
- 支持声音设计、声音克隆和自定义声音功能
- 移除模型自动下载功能，固定模型读取路径

## 相关链接

- 工作流体验地址：[https://www.runninghub.cn/post/2014536001888198657/inviteCode=rh-v1127](https://www.runninghub.cn/post/2014536001888198657/inviteCode=rh-v1127)
- 推荐ComfyUI云平台，通过这个地址注册送1000点算力：[https://www.runninghub.cn/user-center/1887871050510716930/webapp?inviteCode=rh-v1127](https://www.runninghub.cn/user-center/1887871050510716930/webapp?inviteCode=rh-v1127)
- 已注册还未绑定邀请码可绑定邀请码：rh-v1127 赠送1000点算力
- ComfyUI资源分享：[https://pan.quark.cn/s/a56c5a6ec9c2](https://pan.quark.cn/s/a56c5a6ec9c2)
