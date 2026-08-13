import os

# Keep API tests from flaking on the default IP rate limit
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")

from app.config import get_settings

get_settings.cache_clear()
