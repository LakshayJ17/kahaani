"""SDXL + IP-Adapter with diffusers, for the consistency experiment on a free GPU
(Kaggle / Colab). Heavy imports happen lazily, so the app never needs torch.

    gen = DiffusersImageGen(ip_adapter_scale=0.6)
    page = gen.generate(prompt, seed=7, ref=hero_png)
"""

import io

from kahaani.cache import DiskCache
from kahaani.providers.image_base import ImageGen


class DiffusersImageGen(ImageGen):
    name = "diffusers"
    uses_reference = True

    def __init__(
        self,
        model: str = "stabilityai/stable-diffusion-xl-base-1.0",
        ip_adapter_scale: float | None = 0.6,
        steps: int = 30,
        cache: DiskCache | None = None,
    ):
        tag = f"{model}+ipa{ip_adapter_scale}" if ip_adapter_scale else model
        super().__init__(tag, cache)
        import torch
        from diffusers import AutoPipelineForText2Image

        device = "cuda" if torch.cuda.is_available() else "mps"
        dtype = torch.float16
        self._pipe = AutoPipelineForText2Image.from_pretrained(
            model, torch_dtype=dtype, variant="fp16"
        ).to(device)
        self._device = device
        self._scale = ip_adapter_scale
        self._steps = steps
        if ip_adapter_scale:
            self._pipe.load_ip_adapter(
                "h94/IP-Adapter", subfolder="sdxl_models", weight_name="ip-adapter_sdxl.bin"
            )
            self._pipe.set_ip_adapter_scale(ip_adapter_scale)

    def _generate(self, prompt: str, seed: int | None, ref: bytes | None, size: int) -> bytes:
        import torch
        from PIL import Image

        gen = torch.Generator(self._device).manual_seed(seed or 0)
        kwargs = {}
        if self._scale:
            if ref is None:
                # IP-Adapter is loaded, so it needs an image; a blank one = no conditioning.
                self._pipe.set_ip_adapter_scale(0.0)
                kwargs["ip_adapter_image"] = Image.new("RGB", (224, 224), "white")
            else:
                self._pipe.set_ip_adapter_scale(self._scale)
                kwargs["ip_adapter_image"] = Image.open(io.BytesIO(ref)).convert("RGB")
        image = self._pipe(
            prompt=prompt,
            negative_prompt="text, letters, words, watermark, signature, scary, blurry",
            num_inference_steps=self._steps,
            width=size,
            height=size,
            generator=gen,
            **kwargs,
        ).images[0]
        buf = io.BytesIO()
        image.save(buf, "PNG")
        return buf.getvalue()
