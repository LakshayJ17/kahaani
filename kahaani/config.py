"""Settings read from environment variables (and a local .env file)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_GEMINI_MODELS = "gemini-3.8-flash,gemini-3.5-flash,gemini-3.5-flash-lite"
# Lite first: image checks are simple and lite has the most free quota.
DEFAULT_VISION_MODELS = "gemini-3.5-flash-lite,gemini-3.8-flash"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_models: tuple[str, ...]
    groq_api_key: str | None
    groq_model: str
    llm_order: tuple[str, ...]
    cache_dir: Path
    cache_enabled: bool
    vision_models: tuple[str, ...] = field(default_factory=tuple)
    image_provider: str = "cloudflare"
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-2-klein-4b"
    tts_rate: str = "-10%"
    # If the vision check can't run (e.g. quota used up), still deliver the book
    # but warn the parent. Set to 1 to refuse instead.
    require_image_check: bool = False
    books_per_ip_per_day: int = 3  # per signed-in account, despite the old name
    global_books_per_day: int = 60  # protects the shared free quotas from many accounts
    database_url: str = "sqlite:///.data/kahaani.db"
    blob_dir: Path = Path(".data/blobs")
    supabase_url: str | None = None
    supabase_anon_key: str | None = None  # public; the browser uses it for Google sign-in
    supabase_service_key: str | None = None  # secret; storage and account deletion
    url_secret: str | None = None  # signs short-lived picture links


def _csv(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split(",") if p.strip())


def _flag(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "")


def _supabase_base(url: str | None) -> str | None:
    """Accept the project URL with or without a copied API path (e.g. .../rest/v1)."""
    if not url:
        return None
    url = url.strip().rstrip("/")
    for suffix in ("/rest/v1", "/auth/v1", "/storage/v1"):
        url = url.removesuffix(suffix)
    return url


def on_hf_space() -> bool:
    return bool(os.environ.get("SPACE_ID"))


def get_settings() -> Settings:
    env = os.environ.get
    cf_account = env("CLOUDFLARE_ACCOUNT_ID") or None
    cf_token = env("CLOUDFLARE_API_TOKEN") or None
    default_image = "cloudflare" if cf_account and cf_token else "placeholder"
    return Settings(
        gemini_api_key=env("GEMINI_API_KEY") or env("GOOGLE_API_KEY") or None,
        gemini_models=_csv(env("GEMINI_MODEL", DEFAULT_GEMINI_MODELS)),
        groq_api_key=env("GROQ_API_KEY") or None,
        groq_model=env("GROQ_MODEL", "openai/gpt-oss-120b"),
        llm_order=tuple(p.lower() for p in _csv(env("LLM_ORDER", "gemini,groq"))),
        cache_dir=Path(env("KAHAANI_CACHE_DIR", ".cache")),
        # Never keep children's stories on disk in the public app.
        cache_enabled=_flag(env("KAHAANI_CACHE"), default=not on_hf_space()),
        vision_models=_csv(env("VISION_MODEL", DEFAULT_VISION_MODELS)),
        image_provider=env("IMAGE_PROVIDER", default_image).lower(),
        cloudflare_account_id=cf_account,
        cloudflare_api_token=cf_token,
        cloudflare_image_model=env(
            "CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b"
        ),
        tts_rate=env("TTS_RATE", "-10%"),
        require_image_check=_flag(env("REQUIRE_IMAGE_CHECK"), default=False),
        books_per_ip_per_day=int(env("BOOKS_PER_DAY", env("BOOKS_PER_IP_PER_DAY", "3"))),
        global_books_per_day=int(env("GLOBAL_BOOKS_PER_DAY", "60")),
        database_url=env("DATABASE_URL", "sqlite:///.data/kahaani.db"),
        blob_dir=Path(env("KAHAANI_BLOB_DIR", ".data/blobs")),
        supabase_url=_supabase_base(env("SUPABASE_URL")),
        # New-style keys (publishable / secret) or legacy ones (anon / service_role) both work.
        supabase_anon_key=env("SUPABASE_PUBLISHABLE_KEY") or env("SUPABASE_ANON_KEY") or None,
        supabase_service_key=env("SUPABASE_SECRET_KEY") or env("SUPABASE_SERVICE_KEY") or None,
        url_secret=env("KAHAANI_URL_SECRET") or None,
    )
