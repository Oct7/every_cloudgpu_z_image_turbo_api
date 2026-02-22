import torch
from diffusers import ZImagePipeline

print("Downloading and caching Z-Image-Turbo model...")
# Using diffusers pipeline to prepopulate huggingface cache
pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
print("Model prepopulated successfully!")
