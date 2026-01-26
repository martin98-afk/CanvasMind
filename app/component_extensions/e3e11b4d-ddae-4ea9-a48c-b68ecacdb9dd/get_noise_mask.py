import torch

# ----------------------------------------------------------------
# 基础工具类与辅助函数 (同步 ComfyUI 内部逻辑)
# ----------------------------------------------------------------

def get_noise_mask(latent):
    noise_mask = latent.get("noise_mask", None)
    latent_image = latent["samples"]
    if noise_mask is None:
        batch_size, _, latent_length, _, _ = latent_image.shape
        noise_mask = torch.ones((batch_size, 1, latent_length, 1, 1), 
                                dtype=torch.float32, device=latent_image.device)
    else:
        noise_mask = noise_mask.clone()
    return noise_mask