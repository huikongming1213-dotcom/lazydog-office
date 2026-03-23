"""
Publisher Service — STUB
Interfaces for publishing to social platforms.
Real implementations to be added per platform.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PublishResult:
    def __init__(self, platform: str, success: bool, post_url: str | None = None, error: str | None = None):
        self.platform = platform
        self.success = success
        self.post_url = post_url
        self.error = error
        self.published_at = datetime.utcnow() if success else None


async def publish_post(
    platform: str,
    caption: str,
    image_url: str,
    hashtags: list[str],
    job_id: str,
) -> PublishResult:
    """
    STUB: Publish a post to the given platform.
    Replace each platform block with real API calls.

    Supported platforms: ig, linkedin, x, threads, fb
    """
    logger.info(f"[Publisher] STUB publishing to {platform} for job={job_id}")

    # ── Instagram (Meta Graph API) ─────────────────────────────────────────────
    if platform == "ig":
        # TODO: Implement Meta Graph API
        # 1. Upload image to IG container: POST /{ig-user-id}/media
        # 2. Publish container: POST /{ig-user-id}/media_publish
        return _stub_result(platform, job_id)

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    elif platform == "linkedin":
        # TODO: Implement LinkedIn API v2
        # POST /ugcPosts with media upload
        return _stub_result(platform, job_id)

    # ── X (Twitter) ───────────────────────────────────────────────────────────
    elif platform == "x":
        # TODO: Implement Twitter API v2
        # POST /2/tweets with media_ids
        return _stub_result(platform, job_id)

    # ── Threads ───────────────────────────────────────────────────────────────
    elif platform == "threads":
        # TODO: Implement Threads API (Meta)
        # Similar flow to IG container approach
        return _stub_result(platform, job_id)

    # ── Facebook ──────────────────────────────────────────────────────────────
    elif platform == "fb":
        # TODO: Implement Meta Graph API
        # POST /{page-id}/photos
        return _stub_result(platform, job_id)

    else:
        logger.warning(f"[Publisher] Unknown platform: {platform}")
        return PublishResult(platform=platform, success=False, error=f"Unknown platform: {platform}")


async def publish_to_all_platforms(
    captions: dict,
    image_url: str,
    hashtags: list[str],
    job_id: str,
    platforms: list[str] | None = None,
) -> dict[str, PublishResult]:
    """Publish to all specified platforms concurrently."""
    import asyncio

    target_platforms = platforms or list(captions.keys())
    tasks = {
        p: publish_post(p, captions.get(p, ""), image_url, hashtags, job_id)
        for p in target_platforms
        if p in captions
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return dict(zip(tasks.keys(), results))


def _stub_result(platform: str, job_id: str) -> PublishResult:
    logger.info(f"[Publisher] STUB: Would publish to {platform} (job={job_id})")
    return PublishResult(
        platform=platform,
        success=True,
        post_url=f"https://stub.example.com/{platform}/{job_id}",
    )
