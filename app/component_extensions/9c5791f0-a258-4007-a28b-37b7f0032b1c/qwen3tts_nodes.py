import os
import sys
import torch
import random
import numpy as np
import folder_paths
import gc
import shutil

# 添加本地 qwen_tts 目录到 Python 路径（参考 ComfyUI-Qwen-TTS 的方式）
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 尝试导入 qwen_tts（参考 ComfyUI-Qwen-TTS 的导入方式）
try:
    from ._qwen_tts_haigc import Qwen3TTSModel
except (ImportError, ValueError):
    try:
        from _qwen_tts_haigc import Qwen3TTSModel
    except ImportError as e:
        import traceback
        print(f"❌ Failed to import Qwen3-TTS: {e}")
        traceback.print_exc()
        print("Please ensure the qwen_tts package is present in the plugin directory.")
        raise

# Helper to convert ComfyUI audio to numpy
def comfy_audio_to_numpy(audio_dict):
    if audio_dict is None:
        return None
    waveform = audio_dict['waveform'] # [batch, channels, samples]
    sample_rate = audio_dict['sample_rate']
    
    # Take the first item in batch and mix down to mono if needed, or keep as is?
    # Qwen might expect mono.
    # waveform is tensor.
    
    # Use the first batch
    wav = waveform[0]
    
    # If stereo, mix to mono?
    if wav.shape[0] > 1:
        wav = torch.mean(wav, dim=0, keepdim=True)
        
    wav_np = wav.squeeze().cpu().numpy()
    return (wav_np, sample_rate)

LANGUAGE_MAP = {
    "自动": "auto",
    "中文": "Chinese",
    "英文": "English",
    "日文": "Japanese",
    "韩文": "Korean",
    "德文": "German",
    "法文": "French",
    "俄文": "Russian",
    "葡萄牙文": "Portuguese",
    "西班牙文": "Spanish",
    "意大利文": "Italian",
}
LANGUAGE_OPTIONS = list(LANGUAGE_MAP.keys())
SEED_CONTROL_OPTIONS = ["固定", "增加", "减少", "随机"]

def resolve_seed_state(obj, seed, mode):
    try:
        seed_value = int(seed)
    except (TypeError, ValueError):
        seed_value = 0
    if not hasattr(obj, "_seed_base"):
        obj._seed_base = seed_value
        obj._seed_state = seed_value
    if seed_value != obj._seed_base:
        obj._seed_base = seed_value
        obj._seed_state = seed_value
    if mode == "随机":
        seed_value = random.randint(0, 2**31 - 1)
        obj._seed_state = seed_value
        return seed_value
    if mode == "增加":
        seed_value = int(obj._seed_state)
        obj._seed_state = seed_value + 1
        return seed_value
    if mode == "减少":
        seed_value = int(obj._seed_state)
        obj._seed_state = seed_value - 1
        return seed_value
    obj._seed_state = seed_value
    return seed_value

def apply_seed(seed_value):
    seed_value = int(seed_value) & 0xFFFFFFFF
    random.seed(seed_value)
    np.random.seed(seed_value)
    torch.manual_seed(seed_value)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed_value)
    return seed_value

class Qwen3TTSModelLoader:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "模型名称": ([
                    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
                    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                    "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                ],),
                "运行设备": (["cuda", "cpu", "auto"], {"default": "cuda"}),
                "精度": (["fp16", "fp32"], {"default": "fp16"}),
            }
        }

    RETURN_TYPES = ("QWEN3_TTS_MODEL",)
    RETURN_NAMES = ("模型",)
    FUNCTION = "load_model"
    CATEGORY = "Qwen3TTS"
    DESCRIPTION = "加载 Qwen3-TTS 模型。模型必须已存在于 ComfyUI/models/Qwen3TTS 目录中。"

    def load_model(self, 模型名称, 运行设备, 精度):
        model_name = 模型名称
        device = 运行设备
        precision = 精度
        
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"Loading Qwen3TTS model: {model_name} on {device}...")
        
        # 固定模型读取路径：ComfyUI/models/qwen-tts
        qwen_models_dir = os.path.join(folder_paths.models_dir, "qwen-tts")
        
        # Clean model folder name (remove "Qwen/" prefix)
        # e.g. "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign" -> "Qwen3-TTS-12Hz-1.7B-VoiceDesign"
        model_folder_name = model_name.split("/")[-1]
        model_path = os.path.join(qwen_models_dir, model_folder_name)
        
        # Check for "messy" folder name from previous downloads (e.g., "1.7B" -> "1__7B")
        # 兼容旧版本的文件夹命名
        if not os.path.exists(model_path) or not os.path.isdir(model_path):
            messy_folder_name = model_folder_name.replace(".", "__")
            
            possible_messy_paths = [
                os.path.join(qwen_models_dir, messy_folder_name),
                os.path.join(qwen_models_dir, model_folder_name.replace("1.7B", "1__7B")),
                os.path.join(qwen_models_dir, model_folder_name.replace("0.6B", "0__6B")),
                os.path.join(qwen_models_dir, model_folder_name.replace("1.7B", "1-7B")),
                os.path.join(qwen_models_dir, model_folder_name.replace("0.6B", "0-6B")),
                os.path.join(qwen_models_dir, model_folder_name.replace(".", "-")),
            ]
            
            for bad_path in possible_messy_paths:
                if os.path.exists(bad_path) and os.path.isdir(bad_path):
                    print(f"Found legacy model folder: {bad_path}. Renaming to {model_path}...")
                    try:
                        shutil.move(bad_path, model_path)
                        break
                    except Exception as e:
                        print(f"Failed to rename folder: {e}")
        
        # 检查模型路径是否存在
        if not os.path.exists(model_path) or not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"模型未找到: {model_path}\n"
                f"请确保模型已下载到: {qwen_models_dir}\n"
                f"模型文件夹名称应为: {model_folder_name}"
            )
        
        # Load model using ComfyUI cache
        # RH: 强制使用本地文件，禁用下载功能（参考 ComfyUI-Qwen-TTS 的加载方式）
        dtype = torch.float16 if precision == "fp16" else torch.float32
        
        # 参考 ComfyUI-Qwen-TTS 的加载方式，但强制使用本地文件
        try:
            # 尝试使用 device_map 和 attn_implementation（如果支持）
            model = Qwen3TTSModel.from_pretrained(
                model_path, 
                device_map=device, 
                dtype=dtype,
                cache_dir=qwen_models_dir,
                local_files_only=True,  # RH: 强制仅使用本地文件
                force_download=False,   # RH: 禁用强制下载
                attn_implementation="flash_attention_2"  # 参考 ComfyUI-Qwen-TTS
            )
        except TypeError:
            # Fallback: 如果某些参数不支持，尝试简化版本
            try:
                model = Qwen3TTSModel.from_pretrained(
                    model_path, 
                    device_map=device, 
                    torch_dtype=dtype,
                    cache_dir=qwen_models_dir,
                    local_files_only=True,  # RH: 强制仅使用本地文件
                    force_download=False    # RH: 禁用强制下载
                )
            except TypeError:
                # 最简版本：只使用基本参数
                model = Qwen3TTSModel.from_pretrained(
                    model_path, 
                    cache_dir=qwen_models_dir,
                    local_files_only=True,  # RH: 强制仅使用本地文件
                    force_download=False    # RH: 禁用强制下载
                )
            
        return (model,)

class Qwen3TTSVoiceDesign:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "模型": ("QWEN3_TTS_MODEL",),
                "文本": ("STRING", {"multiline": True, "default": "Hello, this is a test."}),
                "提示词": ("STRING", {"multiline": True, "default": "A young female voice, energetic and bright."}),
            },
            "optional": {
                "语言": (LANGUAGE_OPTIONS, {"default": "自动"}),
                "自动卸载模型": ("BOOLEAN", {"default": False, "label_on": "是", "label_off": "否"}),
                "最大生成Token数": ("INT", {"default": 2048, "min": 64, "max": 8192, "step": 64, "display": "number", "tooltip": "限制生成的最大长度。默认2048，通常足够。设为0则根据文本自动调整（不限制）。"}),
                "随机种子": ("INT", {"default": 0, "min": 0, "max": 4294967295, "step": 1, "display": "number"}),
                "生成后控制": (SEED_CONTROL_OPTIONS, {"default": "固定"}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("音频",)
    FUNCTION = "generate"
    CATEGORY = "Qwen3TTS"
    DESCRIPTION = "使用声音设计（Voice Design）生成语音，基于提示词创建声音。\n⚠️ 需要加载带有 'VoiceDesign' 的模型（如 Qwen3-TTS-12Hz-1.7B-VoiceDesign）。"

    def generate(self, 模型, 文本, 提示词, 语言, 随机种子=0, 生成后控制="固定", 自动卸载模型=False, 最大生成Token数=2048):
        model = 模型
        text = 文本
        instruct = 提示词
        language = 语言
        seed = 随机种子
        seed_control = 生成后控制
        max_new_tokens = 最大生成Token数
        
        language = LANGUAGE_MAP.get(language, language)
        if language == "auto":
            language = None
            
        print(f"Generating Voice Design... Text len: {len(text)}")
        
        # generate_voice_design returns (audio_chunks, sample_rate)
        # audio_chunks is List[numpy.ndarray]
        
        # Handle max_new_tokens logic
        # If user sets it to a valid number, we pass it.
        # If 0 or very large, we might let the model decide, but generate_* usually expects a value or has a default.
        # Qwen-TTS generate methods usually accept kwargs.
        
        kwargs = {}
        if max_new_tokens > 0:
            kwargs["max_new_tokens"] = max_new_tokens
        
        rng_state = torch.get_rng_state()
        cuda_rng_state = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
        np_state = np.random.get_state()
        py_state = random.getstate()
        seed_value = resolve_seed_state(self, seed, seed_control)
        apply_seed(seed_value)

        try:
            outputs, sample_rate = model.generate_voice_design(
                text=text,
                instruct=instruct,
                language=language,
                **kwargs
            )
        except (ValueError, AttributeError) as e:
            error_msg = str(e).lower()
            if "does not support generate_voice_design" in error_msg or "generate_voice_design" in error_msg or "has no attribute" in error_msg:
                raise ValueError(
                    "【Qwen3TTS Error】您当前加载的模型不支持'声音设计(Voice Design)'功能。\n"
                    "请在加载器中选择带有 'VoiceDesign' 的模型：\n"
                    "  - Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign\n\n"
                    "[Qwen3TTS Error] The loaded model does not support 'Voice Design'.\n"
                    "Please select a 'VoiceDesign' model in the Loader:\n"
                    "  - Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
                ) from e
            raise e
        finally:
            if cuda_rng_state is not None:
                torch.cuda.set_rng_state_all(cuda_rng_state)
            torch.set_rng_state(rng_state)
            np.random.set_state(np_state)
            random.setstate(py_state)
            if 自动卸载模型:
                print("Unloading model to CPU...")
                if hasattr(model, "model"):
                    model.model.to("cpu")
                if hasattr(model, "device"):
                    model.device = torch.device("cpu")
                torch.cuda.empty_cache()
                gc.collect()
        
        # Concatenate chunks
        full_audio = np.concatenate(outputs)
        
        # ComfyUI AUDIO format expects {'waveform': tensor, 'sample_rate': int}
        # waveform shape should be [batch_size, channels, samples]
        
        # full_audio is typically [samples] (mono) or [samples, channels]
        # Qwen-TTS usually outputs [samples] for mono audio.
        
        tensor_audio = torch.from_numpy(full_audio).float()
        
        if tensor_audio.ndim == 1:
            # [samples] -> [1, 1, samples]
            tensor_audio = tensor_audio.unsqueeze(0).unsqueeze(0)
        elif tensor_audio.ndim == 2:
            # Check if it's [channels, samples] or [samples, channels]
            # Assuming [samples, channels] from common audio libs, but need to be sure.
            # If [samples, channels], we want [1, channels, samples]
            if tensor_audio.shape[0] > tensor_audio.shape[1]: 
                # Likely [samples, channels]
                tensor_audio = tensor_audio.permute(1, 0).unsqueeze(0)
            else:
                # Likely [channels, samples]
                tensor_audio = tensor_audio.unsqueeze(0)
                
        return ({"waveform": tensor_audio, "sample_rate": sample_rate},)

class Qwen3TTSVoiceClone:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "模型": ("QWEN3_TTS_MODEL",),
                "文本": ("STRING", {"multiline": True, "default": "Hello, I am cloning this voice."}),
                "参考音频": ("AUDIO",),
            },
            "optional": {
                "参考文本": ("STRING", {"multiline": True, "default": ""}),
                "语言": (LANGUAGE_OPTIONS, {"default": "自动"}),
                "自动卸载模型": ("BOOLEAN", {"default": False, "label_on": "是", "label_off": "否"}),
                "最大生成Token数": ("INT", {"default": 2048, "min": 64, "max": 8192, "step": 64, "display": "number", "tooltip": "限制生成的最大长度。默认2048，通常足够。设为0则根据文本自动调整（不限制）。"}),
                "随机种子": ("INT", {"default": 0, "min": 0, "max": 4294967295, "step": 1, "display": "number"}),
                "生成后控制": (SEED_CONTROL_OPTIONS, {"default": "固定"}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("音频",)
    FUNCTION = "generate"
    CATEGORY = "Qwen3TTS"
    DESCRIPTION = "使用声音克隆（Voice Clone）生成语音，基于参考音频。\n⚠️ 需要加载带有 'Base' 的模型（如 Qwen3-TTS-12Hz-1.7B-Base）。"

    def generate(self, 模型, 文本, 参考音频, 参考文本, 语言, 随机种子=0, 生成后控制="固定", 自动卸载模型=False, 最大生成Token数=2048):
        model = 模型
        text = 文本
        reference_audio = 参考音频
        reference_text = 参考文本
        language = 语言
        seed = 随机种子
        seed_control = 生成后控制
        max_new_tokens = 最大生成Token数
        
        language = LANGUAGE_MAP.get(language, language)
        if language == "auto":
            language = None
        if not reference_text.strip():
            reference_text = None
            
        print(f"Generating Voice Clone... Text len: {len(text)}")
        
        # Convert ref audio
        ref_audio_np_tuple = comfy_audio_to_numpy(reference_audio)
        
        kwargs = {}
        if max_new_tokens > 0:
            kwargs["max_new_tokens"] = max_new_tokens
            
        rng_state = torch.get_rng_state()
        cuda_rng_state = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
        np_state = np.random.get_state()
        py_state = random.getstate()
        seed_value = resolve_seed_state(self, seed, seed_control)
        apply_seed(seed_value)

        try:
            outputs, sample_rate = model.generate_voice_clone(
                text=text,
                ref_audio=ref_audio_np_tuple,
                ref_text=reference_text,
                language=language,
                **kwargs
            )
        except (ValueError, AttributeError) as e:
            error_msg = str(e).lower()
            if "does not support generate_voice_clone" in error_msg or "generate_voice_clone" in error_msg or "has no attribute" in error_msg:
                raise ValueError(
                    "【Qwen3TTS Error】您当前加载的模型不支持'声音克隆(Voice Clone)'功能。\n"
                    "请在加载器中选择带有 'Base' 的模型：\n"
                    "  - Qwen/Qwen3-TTS-12Hz-1.7B-Base\n"
                    "  - Qwen/Qwen3-TTS-12Hz-0.6B-Base\n\n"
                    "[Qwen3TTS Error] The loaded model does not support 'Voice Clone'.\n"
                    "Please select a 'Base' model in the Loader:\n"
                    "  - Qwen/Qwen3-TTS-12Hz-1.7B-Base\n"
                    "  - Qwen/Qwen3-TTS-12Hz-0.6B-Base"
                ) from e
            raise e
        finally:
            if cuda_rng_state is not None:
                torch.cuda.set_rng_state_all(cuda_rng_state)
            torch.set_rng_state(rng_state)
            np.random.set_state(np_state)
            random.setstate(py_state)
            if 自动卸载模型:
                print("Unloading model to CPU...")
                if hasattr(model, "model"):
                    model.model.to("cpu")
                if hasattr(model, "device"):
                    model.device = torch.device("cpu")
                torch.cuda.empty_cache()
                gc.collect()
        
        full_audio = np.concatenate(outputs)
        
        # ComfyUI AUDIO format expects {'waveform': tensor, 'sample_rate': int}
        # waveform shape should be [batch_size, channels, samples]
        
        tensor_audio = torch.from_numpy(full_audio).float()
        
        if tensor_audio.ndim == 1:
            # [samples] -> [1, 1, samples]
            tensor_audio = tensor_audio.unsqueeze(0).unsqueeze(0)
        elif tensor_audio.ndim == 2:
            if tensor_audio.shape[0] > tensor_audio.shape[1]: 
                # Likely [samples, channels] -> [1, channels, samples]
                tensor_audio = tensor_audio.permute(1, 0).unsqueeze(0)
            else:
                # Likely [channels, samples] -> [1, channels, samples]
                tensor_audio = tensor_audio.unsqueeze(0)
                
        return ({"waveform": tensor_audio, "sample_rate": sample_rate},)

class Qwen3TTSCustomVoice:
    SPEAKER_PRESETS = {
        "Vivian": "Bright, slightly edgy young female voice.",
        "Serena": "Warm, gentle young female voice.",
        "Uncle_Fu": "Seasoned male voice with a low, mellow timbre.",
        "Dylan": "Youthful Beijing male voice with a clear, natural timbre.",
        "Eric": "Lively Chengdu male voice with a slightly husky brightness.",
        "Ryan": "Dynamic male voice with strong rhythmic drive.",
        "Aiden": "Sunny American male voice with a clear midrange.",
        "Ono_Anna": "Playful Japanese female voice with a light, nimble timbre.",
        "Sohee": "Warm Korean female voice with rich emotion.",
    }

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "模型": ("QWEN3_TTS_MODEL",),
                "文本": ("STRING", {"multiline": True, "default": "Hello, this is a custom voice."}),
                "预设说话人": (list(s.SPEAKER_PRESETS.keys()), {"default": "Vivian"}),
            },
            "optional": {
                "语言": (LANGUAGE_OPTIONS, {"default": "自动"}),
                "提示词": ("STRING", {"multiline": True, "default": ""}),
                "自动卸载模型": ("BOOLEAN", {"default": False, "label_on": "是", "label_off": "否"}),
                "最大生成Token数": ("INT", {"default": 2048, "min": 64, "max": 8192, "step": 64, "display": "number", "tooltip": "限制生成的最大长度。默认2048，通常足够。设为0则根据文本自动调整（不限制）。"}),
                "随机种子": ("INT", {"default": 0, "min": 0, "max": 4294967295, "step": 1, "display": "number"}),
                "生成后控制": (SEED_CONTROL_OPTIONS, {"default": "固定"}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("音频",)
    FUNCTION = "generate"
    CATEGORY = "Qwen3TTS"
    DESCRIPTION = "使用自定义声音（Custom Voice）生成语音，支持预设说话人。\n⚠️ 需要加载带有 'CustomVoice' 的模型（如 Qwen3-TTS-12Hz-1.7B-CustomVoice）。"

    def generate(self, 模型, 文本, 预设说话人, 语言, 提示词, 随机种子=0, 生成后控制="固定", 自动卸载模型=False, 最大生成Token数=2048):
        model = 模型
        text = 文本
        speaker = 预设说话人
        language = 语言
        instruct = 提示词
        seed = 随机种子
        seed_control = 生成后控制
        max_new_tokens = 最大生成Token数
        
        language = LANGUAGE_MAP.get(language, language)
        if language == "auto":
            language = None
            
        # Handle speaker preset instruction
        # For CustomVoice, the 'speaker' param is the ID/Name used by the model.
        # But we also want to inject the 'instruct' if provided by our preset.
        
        user_instruct = (instruct or "").strip()
        if user_instruct:
            instruct = user_instruct
            print(f"User provided manual instruct, overriding preset for '{speaker}'.")
        else:
            if speaker in self.SPEAKER_PRESETS:
                preset_instruct = self.SPEAKER_PRESETS[speaker]
                if preset_instruct:
                    instruct = preset_instruct
                    print(f"Using preset instruct for '{speaker}': {instruct}")
            if not (instruct or "").strip():
                instruct = None
            
        print(f"Generating Custom Voice: {speaker}...")
        
        # Check if speaker is valid? 
        # model.get_supported_speakers()
        
        kwargs = {}
        if max_new_tokens > 0:
            kwargs["max_new_tokens"] = max_new_tokens
            
        rng_state = torch.get_rng_state()
        cuda_rng_state = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
        np_state = np.random.get_state()
        py_state = random.getstate()
        seed_value = resolve_seed_state(self, seed, seed_control)
        apply_seed(seed_value)

        try:
            outputs, sample_rate = model.generate_custom_voice(
                text=text,
                speaker=speaker,
                instruct=instruct,
                language=language,
                **kwargs
            )
        except (ValueError, AttributeError) as e:
            error_msg = str(e).lower()
            if "does not support generate_custom_voice" in error_msg or "generate_custom_voice" in error_msg or "has no attribute" in error_msg:
                raise ValueError(
                    "【Qwen3TTS Error】您当前加载的模型不支持'自定义声音(Custom Voice)'功能。\n"
                    "请在加载器中选择带有 'CustomVoice' 的模型：\n"
                    "  - Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice\n"
                    "  - Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice\n\n"
                    "[Qwen3TTS Error] The loaded model does not support 'Custom Voice'.\n"
                    "Please select a 'CustomVoice' model in the Loader:\n"
                    "  - Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice\n"
                    "  - Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
                ) from e
            raise e
        finally:
            if cuda_rng_state is not None:
                torch.cuda.set_rng_state_all(cuda_rng_state)
            torch.set_rng_state(rng_state)
            np.random.set_state(np_state)
            random.setstate(py_state)
            if 自动卸载模型:
                print("Unloading model to CPU...")
                if hasattr(model, "model"):
                    model.model.to("cpu")
                if hasattr(model, "device"):
                    model.device = torch.device("cpu")
                torch.cuda.empty_cache()
                gc.collect()
        
        full_audio = np.concatenate(outputs)
        
        # ComfyUI AUDIO format expects {'waveform': tensor, 'sample_rate': int}
        # waveform shape should be [batch_size, channels, samples]
        
        tensor_audio = torch.from_numpy(full_audio).float()
        
        if tensor_audio.ndim == 1:
            # [samples] -> [1, 1, samples]
            tensor_audio = tensor_audio.unsqueeze(0).unsqueeze(0)
        elif tensor_audio.ndim == 2:
            if tensor_audio.shape[0] > tensor_audio.shape[1]: 
                # Likely [samples, channels] -> [1, channels, samples]
                tensor_audio = tensor_audio.permute(1, 0).unsqueeze(0)
            else:
                # Likely [channels, samples] -> [1, channels, samples]
                tensor_audio = tensor_audio.unsqueeze(0)
                
        return ({"waveform": tensor_audio, "sample_rate": sample_rate},)

NODE_CLASS_MAPPINGS = {
    "Qwen3TTSModelLoader": Qwen3TTSModelLoader,
    "Qwen3TTSVoiceDesign": Qwen3TTSVoiceDesign,
    "Qwen3TTSVoiceClone": Qwen3TTSVoiceClone,
    "Qwen3TTSCustomVoice": Qwen3TTSCustomVoice,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen3TTSModelLoader": "Qwen3 TTS 模型加载",
    "Qwen3TTSVoiceDesign": "Qwen3 TTS 声音设计",
    "Qwen3TTSVoiceClone": "Qwen3 TTS 声音克隆",
    "Qwen3TTSCustomVoice": "Qwen3 TTS 自定义声音",
}
