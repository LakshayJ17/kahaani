from kahaani.cache import DiskCache
from kahaani.config import Settings, get_settings
from kahaani.providers.image_base import ImageGen


def build_image_gen(settings: Settings | None = None) -> ImageGen:
    s = settings or get_settings()
    cache = DiskCache(s.cache_dir, "img") if s.cache_enabled else None
    if s.image_provider == "cloudflare":
        if not (s.cloudflare_account_id and s.cloudflare_api_token):
            raise ValueError("IMAGE_PROVIDER=cloudflare needs CLOUDFLARE_ACCOUNT_ID and _API_TOKEN")
        from kahaani.providers.image_cloudflare import CloudflareImageGen

        return CloudflareImageGen(
            s.cloudflare_account_id, s.cloudflare_api_token, s.cloudflare_image_model, cache
        )
    if s.image_provider == "diffusers":
        from kahaani.providers.image_diffusers import DiffusersImageGen

        return DiffusersImageGen(cache=cache)
    if s.image_provider == "placeholder":
        from kahaani.providers.image_placeholder import PlaceholderImageGen

        return PlaceholderImageGen(cache)
    raise ValueError(f"unknown IMAGE_PROVIDER {s.image_provider!r}")
