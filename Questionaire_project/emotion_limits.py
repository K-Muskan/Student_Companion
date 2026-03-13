import hashlib
import json
import logging
import time
from typing import Tuple

from django.core.cache import cache

logger = logging.getLogger(__name__)
_degraded_logged = False


def _key(raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"emotion:{digest}"


def _is_degraded_cache() -> bool:
    backend = cache.__class__.__module__.lower()
    return "locmem" in backend or "dummy" in backend


def _warn_degraded_once():
    global _degraded_logged
    if _degraded_logged:
        return
    if _is_degraded_cache():
        logger.warning(
            "emotion_limit_degraded_mode",
            extra={"reason": "cache_backend_not_distributed"},
        )
        _degraded_logged = True


def _ip_count_key(client_ip: str) -> str:
    return _key(f"ip:{client_ip}:connections")


def _assessment_lease_key(assessment_id: int) -> str:
    return _key(f"assessment:{assessment_id}:lease")


def _lease_meta_key(lease_id: str) -> str:
    return _key(f"lease:{lease_id}:meta")


def _lease_seen_key(lease_id: str) -> str:
    return _key(f"lease:{lease_id}:last_seen")


def try_acquire_connection(
    client_ip: str,
    assessment_id: int,
    lease_id: str,
    max_ip: int,
    max_assessment: int,
    ttl_seconds: int = 120,
) -> bool:
    _warn_degraded_once()
    ip_key = _ip_count_key(client_ip)
    assessment_key = _assessment_lease_key(assessment_id)
    lease_meta_key = _lease_meta_key(lease_id)
    lease_seen_key = _lease_seen_key(lease_id)

    cache.add(ip_key, 0, ttl_seconds)
    now = int(time.time())
    existing_lease = cache.get(assessment_key)
    if existing_lease and existing_lease != lease_id and int(max_assessment) <= 1:
        existing_seen = cache.get(_lease_seen_key(str(existing_lease)))
        existing_meta_raw = cache.get(_lease_meta_key(str(existing_lease)))
        stale = False
        try:
            existing_seen_int = int(existing_seen)
            stale = (now - existing_seen_int) > int(ttl_seconds)
        except (TypeError, ValueError):
            stale = True

        if stale:
            release_connection(str(existing_lease), ttl_seconds=ttl_seconds)
        else:
            return False

    ip_count = int(cache.get(ip_key, 0))
    if ip_count >= int(max_ip):
        return False

    try:
        cache.incr(ip_key)
    except ValueError:
        cache.set(ip_key, 1, ttl_seconds)

    cache.set(assessment_key, lease_id, ttl_seconds)
    cache.set(lease_meta_key, json.dumps({"client_ip": client_ip, "assessment_id": assessment_id}), ttl_seconds)
    cache.set(lease_seen_key, now, ttl_seconds)
    return True


def release_connection(lease_id: str, ttl_seconds: int = 120):
    lease_meta_key = _lease_meta_key(lease_id)
    lease_seen_key = _lease_seen_key(lease_id)
    raw_meta = cache.get(lease_meta_key)
    if not raw_meta:
        cache.delete(lease_seen_key)
        return

    try:
        meta = json.loads(raw_meta)
    except (TypeError, ValueError):
        meta = {}

    client_ip = str(meta.get("client_ip", "") or "")
    assessment_id = meta.get("assessment_id")

    if client_ip:
        ip_key = _ip_count_key(client_ip)
        current = int(cache.get(ip_key, 0))
        cache.set(ip_key, max(0, current - 1), ttl_seconds)

    if assessment_id is not None:
        assessment_key = _assessment_lease_key(int(assessment_id))
        existing = cache.get(assessment_key)
        if existing == lease_id:
            cache.delete(assessment_key)

    cache.delete(lease_meta_key)
    cache.delete(lease_seen_key)


def touch_connection(lease_id: str, ttl_seconds: int = 120):
    now = int(time.time())
    lease_seen_key = _lease_seen_key(lease_id)
    cache.set(lease_seen_key, now, ttl_seconds)

    raw_meta = cache.get(_lease_meta_key(lease_id))
    if not raw_meta:
        return
    try:
        meta = json.loads(raw_meta)
    except (TypeError, ValueError):
        return
    assessment_id = meta.get("assessment_id")
    client_ip = str(meta.get("client_ip", "") or "")
    if client_ip:
        cache.set(_ip_count_key(client_ip), max(1, int(cache.get(_ip_count_key(client_ip), 1))), ttl_seconds)
    if assessment_id is not None:
        cache.set(_assessment_lease_key(int(assessment_id)), lease_id, ttl_seconds)


def consume_frame_quota(assessment_id: int, max_frames: int, window_seconds: int) -> Tuple[bool, int]:
    _warn_degraded_once()
    quota_key = _key(f"assessment:{assessment_id}:quota")
    if cache.add(quota_key, 1, window_seconds):
        return True, 1
    try:
        count = int(cache.incr(quota_key))
    except Exception:
        count = int(cache.get(quota_key, 0)) + 1
        cache.set(quota_key, count, window_seconds)
    if count > int(max_frames):
        return False, count
    return True, count
