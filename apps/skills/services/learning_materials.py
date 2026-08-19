import logging
import re
from decimal import Decimal
from urllib.parse import urlparse

import yt_dlp
from django.core.cache import cache as django_cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator

from apps.ai.services import AIProviderClient
from apps.ai.services.ai_utils import parse_json_response
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES
from apps.skills.models import LearningMaterial, SkillLearningMaterial
from apps.skills.services.url_domains import KNOWN_PLATFORMS, PARKING_DOMAINS, YOUTUBE_DOMAINS
from utils.prompt_sanitizer import sanitize_prompt_value

logger = logging.getLogger(__name__)

_TITLE_TRANSLATION_TTL = 60 * 60 * 24 * 30  # 30 days


def _translate_material_title(title: str) -> dict[str, str]:
    """
    Translate a learning material title to Russian and Uzbek via the AI provider.

    Returns {"ru": "...", "uz": "..."} — falls back to the original title on error.
    Returns cached result if available (30-day TTL).
    """
    fallback = {"ru": title, "uz": title}
    if not title:
        return fallback

    cache_key = f"mat_title_translation:{title[:200].lower()}"
    cached = django_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        client = AIProviderClient()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional translator specialising in educational content. "
                    "Translate the given learning resource title into Russian and Uzbek. "
                    "Keep technical terms, brand names, and proper nouns unchanged. "
                    "Return ONLY a raw JSON object with keys 'ru' and 'uz'. No markdown, no explanations."
                ),
            },
            {
                "role": "user",
                "content": f"Translate this title: {title}",
            },
        ]
        response = client.cached_completion(
            messages,
            "mat_title_translate",
            title[:200].lower(),
            temperature=0.0,
            json_mode=True,
        )
        content = response["choices"][0]["message"]["content"]
        parsed = parse_json_response(content)
        if isinstance(parsed, dict):
            result = {
                "ru": (parsed.get("ru") or title)[:500],
                "uz": (parsed.get("uz") or title)[:500],
            }
            django_cache.set(cache_key, result, timeout=_TITLE_TRANSLATION_TTL)
            return result
    except Exception:
        logger.warning("Failed to translate material title '%s'", title[:80])

    return fallback


_url_validator = URLValidator(schemes=["https", "http"])

_YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}([?&].*)?$"
)

_KNOWN_PLATFORMS = KNOWN_PLATFORMS
_PARKING_DOMAINS = PARKING_DOMAINS
_YOUTUBE_DOMAINS = YOUTUBE_DOMAINS

_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist',
    'socket_timeout': 15,
    'cachedir': False,
}


def _sanitize_youtube_text(text: str) -> str:
    """Sanitize user-generated text from YouTube before DB storage."""
    s = (text or "").strip()
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", s)
    return s


def _is_relevant_video(title: str, skill_name: str) -> bool:
    """Check if a video title contains at least one meaningful keyword from the skill name.

    Uses word-boundary matching for short keywords (len <= 3) to avoid false
    substring matches — e.g. 'go' must appear as a whole word, not inside 'django'.
    Without this filter, unrelated high-view videos (music, k8s, etc.) sneak in
    via the Uzbek-language search pool.
    """
    words = {w.lower() for w in re.split(r"\W+", skill_name) if len(w) > 1}
    title_lower = title.lower()
    for w in words:
        pattern = rf"\b{re.escape(w)}\b" if len(w) <= 3 else re.escape(w)
        if re.search(pattern, title_lower):
            return True
    return False


def _extract_youtube_candidates(query: str, skill_name: str) -> list[dict]:
    """Run a single yt-dlp search and return parsed candidate dicts."""
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            result = ydl.extract_info(query, download=False)
            if not result or not result.get('entries'):
                return []
            candidates = []
            for entry in result['entries']:
                video_id = entry.get('id') or ''
                if not video_id:
                    continue
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                title = _sanitize_youtube_text(entry.get('title'))
                if not title:
                    continue
                if not _is_relevant_video(title, skill_name):
                    continue
                view_count = entry.get('view_count', 0) or 0
                duration_sec = entry.get('duration', 0) or 0
                description = _sanitize_youtube_text(entry.get('description'))
                channel = entry.get('channel') or entry.get('uploader') or 'YouTube'
                channel = _sanitize_youtube_text(channel)[:100]
                rating = min(5.0, round(3.5 + (view_count / 50000000) * 1.5, 1))
                relevance_score = min(95, round(50 + (view_count / 5_000_000) * 45))
                material_type = 'course' if duration_sec > 1800 else 'video'
                candidates.append({
                    'title': title,
                    'description': description[:500],
                    'url': video_url,
                    'material_type': material_type,
                    'source': channel,
                    'duration_hours': round(duration_sec / 3600, 2),
                    'is_free': True,
                    'language': 'en',
                    'rating': rating,
                    'relevance_score': relevance_score,
                    '_view_count': view_count,
                })
            return candidates
    except Exception:
        logger.warning("YouTube search failed for query: %s", query)
        return []


def _search_youtube_videos(skill_name: str, max_results: int = 3, language: str = "en") -> list[dict]:
    """Search YouTube for relevant videos, returning the most-viewed ones.

    Always searches in English to get high-quality content. For non-English
    languages also runs a second search in that language and merges, so e.g.
    Russian users get popular Russian-language videos alongside English ones.
    """
    fetch_count = max(max_results * 3, 6)

    # Always fetch English candidates first
    candidates = _extract_youtube_candidates(
        f"ytsearch{fetch_count}:{skill_name} tutorial", skill_name
    )

    # For non-English, also search in that language and merge by URL
    if language != "en":
        lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "")
        if lang_name:
            lang_candidates = _extract_youtube_candidates(
                f"ytsearch{fetch_count}:{skill_name} {lang_name}", skill_name
            )
            seen_urls = {c['url'] for c in candidates}
            for c in lang_candidates:
                if c['url'] not in seen_urls:
                    candidates.append(c)
                    seen_urls.add(c['url'])

    if not candidates:
        return []

    candidates.sort(key=lambda v: v['_view_count'], reverse=True)
    videos = []
    for v in candidates[:max_results]:
        v.pop('_view_count', None)
        videos.append(v)
    return videos


def _yt_video_exists(url: str) -> bool:
    """Quick check if a YouTube video is still available using yt-dlp."""
    check_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'socket_timeout': 10,
        'cachedir': False,
    }
    try:
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return bool(info and info.get('id'))
    except Exception:
        return False


def _get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _normalize_url_for_comparison(url: str) -> str:
    """Normalize URL to (scheme, netloc, path) ignoring query/fragment."""
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        path = parsed.path.rstrip("/") or "/"
        return f"{scheme}://{hostname}{path}"
    except Exception:
        return url.rstrip("/")




def _safe_decimal(value, default=0, max_value=None):
    try:
        d = Decimal(str(value or default))
        if not d.is_finite():
            return Decimal(str(default))
        if max_value is not None and d > max_value:
            return Decimal(str(max_value))
        if d < 0:
            return Decimal("0")
        return d
    except Exception:
        return Decimal(str(default))


def _search_with_ddgs(query: str, language: str = "en", max_results: int = 7) -> list[dict]:
    """Search using ddgs — auto mode first, then explicit backend fallbacks."""
    from ddgs import DDGS

    backends = [None, "yandex", "bing", "brave", "duckduckgo", "startpage"]  # None = auto
    for backend in backends:
        try:
            kwargs = {"max_results": max_results, "region": language}
            if backend:
                kwargs["backend"] = backend
            with DDGS() as ddgs:
                results = list(ddgs.text(query, **kwargs))
                if results:
                    return [
                        {
                            "title": r.get("title", "").strip(),
                            "url": r.get("href", "").strip(),
                            "snippet": (r.get("body") or "").strip()[:300],
                        }
                        for r in results
                        if r.get("href") and r.get("title")
                    ]
        except Exception:
            label = backend or "auto"
            logger.warning("Search backend '%s' failed for query: %s", label, query)
    logger.warning("All search backends failed for query: %s", query)
    return []


def _build_search_query(skill_name: str, language: str, country: str) -> str:
    """Build a targeted search query for learning materials."""
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "")
    parts = [skill_name, "course OR tutorial OR guide OR documentation"]
    if lang_name and language != "en":
        parts.append(lang_name)
    if country:
        parts.append(country)
    return " ".join(parts)


def _format_search_results_for_prompt(results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}")
    return "\n\n".join(lines)


def _generate_without_grounding(skill, ai_client, language: str, country: str = "") -> list:
    """
    Generate learning materials via the AI provider.

    Searches SearXNG first to get real URLs, then asks the AI to curate
    from those results. Falls back to pure hallucination-based generation
    only if SearXNG returns nothing.
    """
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")
    skill_name = sanitize_prompt_value(skill.name_en or skill.name)
    skill_desc = sanitize_prompt_value(skill.description_en or "N/A", max_length=2000)
    country_ctx = (
        f"The candidate is located in {sanitize_prompt_value(country)}. "
        f"Recommend materials relevant to {sanitize_prompt_value(country)} laws, standards, and professional context. "
        f"Do NOT recommend materials based on another country's jurisdiction or regulations.\n"
        if country else ""
    )

    search_results = _search_with_ddgs(
        _build_search_query(skill.name_en or skill.name, language, country),
        language=language,
        max_results=10,
    )

    if search_results:
        results_text = _format_search_results_for_prompt(search_results)
        user_content = (
            f"Skill: {skill_name}\n"
            f"Skill description: {skill_desc}\n\n"
            f"{country_ctx}"
            f"Here are real search results for this skill:\n\n{results_text}\n\n"
            f"From these results, select 3-5 materials that are most directly relevant to '{skill_name}'. "
            f"ONLY use URLs from the search results above — do not invent or modify any URL. "
            "Prefer free, accessible materials under 20 hours. "
            f"Prefer materials in {lang_name}, falling back to English if needed.\n\n"
            "For each selected material provide:\n"
            "- title, description (1-2 sentences), url (exactly as shown above),\n"
            "- material_type (course/video/article/documentation), source (platform name),\n"
            "- duration_hours (decimal), is_free (boolean),\n"
            f"- language ('en' or '{language}'), rating (0-5), relevance_score (0-100),\n"
            f"- relevance_reason (in {lang_name}, 1 sentence)\n\n"
            "Do NOT include any YouTube URLs. Respond in JSON with a 'materials' array."
        )
        system_content = (
            "You are a learning resource curator. Select the best materials from the provided search results. "
            "Use ONLY the URLs given — never invent URLs. Return JSON with a 'materials' array."
        )
    else:
        logger.warning("SearXNG returned no results for skill %s — falling back to hallucination", skill.name_en)
        user_content = (
            f"Skill: {skill_name}\n"
            f"Skill description: {skill_desc}\n\n"
            f"{country_ctx}"
            f"Search primarily for materials in {lang_name}. "
            f"If there are not enough high-quality materials in {lang_name}, include English materials as well.\n"
            "CRITICAL: Every material must be specifically and directly about this skill.\n"
            "Prefer free or easily accessible materials under 20 hours.\n\n"
            "Recommend 3-5 learning materials. For each provide:\n"
            "- title, description (1-2 sentences), url (MUST be a real valid URL),\n"
            "- material_type (course/video/article/documentation), source,\n"
            "- duration_hours, is_free, "
            f"language ('en' or '{language}'), rating (0-5), relevance_score (0-100),\n"
            f"- relevance_reason (in {lang_name})\n\n"
            "Do NOT include YouTube URLs. Respond in JSON with a 'materials' array."
        )
        system_content = (
            "You are a learning resource curator. Recommend high-quality, real learning materials. "
            "All URLs must be valid, existing URLs from well-known platforms. "
            "Return JSON with a 'materials' array."
        )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    try:
        response = ai_client.chat_completion(messages, temperature=0.3, json_mode=True)
        content = response["choices"][0]["message"]["content"]
        parsed = parse_json_response(content)
    except Exception:
        logger.exception("Failed to generate learning materials for skill %s", skill.id)
        return _add_youtube_videos(skill, language)

    materials = _save_materials(skill, parsed, language)
    materials.extend(_add_youtube_videos(skill, language))
    return materials


def _save_materials(skill, parsed: dict, language: str = "en") -> list:
    """Validate and save learning materials to the database."""
    materials_data = parsed.get("materials", [])
    created_materials = []

    for mat_data in materials_data:
        url = mat_data.get("url", "").strip()
        title = mat_data.get("title", "").strip()
        if not url or not title:
            logger.warning("Skipping material with empty URL or title: %s", title or url)
            continue

        domain = _get_domain(url)
        if domain in {"youtube.com", "www.youtube.com", "youtu.be"}:
            logger.debug("Skipping YouTube URL from AI response: %s", url)
            continue

        try:
            _url_validator(url)
        except DjangoValidationError:
            logger.warning("Skipping invalid URL (domain=%s): %s", _get_domain(url), url)
            continue

        domain = _get_domain(url)

        if domain in _YOUTUBE_DOMAINS:
            logger.debug("Skipping YouTube URL from AI response: %s", url)
            continue

        if domain in _PARKING_DOMAINS:
            logger.warning("Skipping parking domain URL: %s", url)
            continue

        material_type = mat_data.get("material_type", "")
        valid_types = {c[0] for c in LearningMaterial.MaterialType.choices}
        if material_type not in valid_types:
            material_type = LearningMaterial.MaterialType.ARTICLE

        raw_lang = mat_data.get("language", language)
        if len(raw_lang) > 5 or not raw_lang.isascii():
            raw_lang = language

        translations = _translate_material_title(title)
        material, _ = LearningMaterial.objects.get_or_create(
            url=url,
            defaults={
                "title": title,
                "title_ru": translations["ru"],
                "title_uz": translations["uz"],
                "description": mat_data.get("description", ""),
                "material_type": material_type,
                "source": mat_data.get("source", ""),
                "duration_hours": _safe_decimal(mat_data.get("duration_hours"), max_value=10000),
                "language": raw_lang,
                "rating": _safe_decimal(mat_data.get("rating"), max_value=5),
                "is_free": mat_data.get("is_free", True),
                "is_active": True,
            },
        )

        relevance_score = mat_data.get("relevance_score", 0) or 0
        slm, _ = SkillLearningMaterial.objects.get_or_create(
            skill=skill,
            material=material,
            defaults={
                "relevance_score": _safe_decimal(relevance_score, max_value=100),
                "is_top_match": bool(relevance_score >= 80),
                "relevance_reason": mat_data.get("relevance_reason", ""),
            },
        )

        created_materials.append(slm)

    return created_materials


def _save_youtube_materials(skill, video_dicts: list[dict], language: str = "en") -> list:
    """Save YouTube search results as learning materials."""
    created = []

    for vid in video_dicts:
        url = vid.get("url", "").strip()
        title = vid.get("title", "").strip()
        if not url or not title:
            continue

        try:
            _url_validator(url)
        except DjangoValidationError:
            continue

        if not _YOUTUBE_URL_RE.match(url):
            logger.warning("Skipping non-YouTube URL from yt-dlp: %s", url)
            continue

        if not _yt_video_exists(url):
            logger.warning("Skipping unavailable YouTube video: %s", url)
            continue

        material_type = vid.get("material_type", "video")
        valid_types = {c[0] for c in LearningMaterial.MaterialType.choices}
        if material_type not in valid_types:
            material_type = LearningMaterial.MaterialType.VIDEO

        raw_lang = vid.get("language", language)
        if len(raw_lang) > 5 or not raw_lang.isascii():
            raw_lang = language

        translations = _translate_material_title(title)
        material, _ = LearningMaterial.objects.get_or_create(
            url=url,
            defaults={
                "title": title,
                "title_ru": translations["ru"],
                "title_uz": translations["uz"],
                "description": vid.get("description", ""),
                "material_type": material_type,
                "source": vid.get("source", "YouTube"),
                "duration_hours": _safe_decimal(vid.get("duration_hours"), max_value=10000),
                "language": raw_lang,
                "rating": _safe_decimal(vid.get("rating"), max_value=5),
                "is_free": True,
                "is_active": True,
            },
        )

        relevance_score = vid.get("relevance_score", 75) or 75
        slm, _ = SkillLearningMaterial.objects.get_or_create(
            skill=skill,
            material=material,
            defaults={
                "relevance_score": _safe_decimal(relevance_score, max_value=100),
                "is_top_match": bool(relevance_score >= 80),
                "relevance_reason": vid.get("relevance_reason", ""),
            },
        )

        created.append(slm)

    return created


def generate_learning_materials_for_skill(skill, ai_client, language="en", country=""):
    return _generate_without_grounding(skill, ai_client, language, country)


def _add_youtube_videos(skill, language: str) -> list:
    """Search YouTube and add/refresh videos for a skill. Returns list of SLM objects."""
    # Always search in English — the best tech content is in English regardless of user language.
    # yt-dlp Uzbek/Russian searches return only small local channels with very few views.
    youtube_videos = _search_youtube_videos(
        sanitize_prompt_value(skill.name_en or skill.name, max_length=100),
        max_results=2,
        language="en",
    )
    if not youtube_videos:
        return []

    # Find existing YouTube SLM records for this skill so we can replace low-quality ones
    existing_yt_slms = list(
        SkillLearningMaterial.objects.filter(
            skill=skill,
            material__url__iregex=r'youtube\.com|youtu\.be',
        ).select_related("material")
    )
    existing_yt_urls = {slm.material.url for slm in existing_yt_slms}

    # Determine which videos are genuinely new
    new_videos = [v for v in youtube_videos if v['url'] not in existing_yt_urls]

    # If all top videos are already saved, nothing to do
    if not new_videos and existing_yt_slms:
        return existing_yt_slms

    # If we have stale low-quality records (rating 3.5 = essentially 0 views) and found better
    # ones, delete the stale records to make room for the new ones
    if new_videos and existing_yt_slms:
        stale = [
            slm for slm in existing_yt_slms
            if float(slm.material.rating or 0) <= 3.5
        ]
        if stale:
            stale_ids = [slm.id for slm in stale]
            SkillLearningMaterial.objects.filter(id__in=stale_ids).delete()
            logger.info(
                "YouTube: removed %d stale low-quality videos for skill '%s'",
                len(stale_ids), skill.name,
            )

    saved = _save_youtube_materials(skill, new_videos, language)
    if saved:
        logger.info(
            "YouTube: added %d videos for skill '%s' (id=%s)",
            len(saved), skill.name, skill.id,
        )
    return saved


def _process_roadmap_item(item, ai_client, language, country):
    if not item.skill:
        return
    if SkillLearningMaterial.objects.filter(skill=item.skill, material__language=language).exists():
        _add_youtube_videos(item.skill, language)
        return
    try:
        generate_learning_materials_for_skill(item.skill, ai_client, language, country)
    except Exception:
        logger.exception(
            "Failed to generate materials for roadmap item %s (skill: %s)",
            item.id, item.skill_name,
        )


def generate_learning_materials_for_roadmap(roadmap, ai_model="default", language="en", country=""):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ai_client = AIProviderClient()
    items = [item for item in roadmap.items.select_related("skill").all() if item.skill]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_process_roadmap_item, item, ai_client, language, country): item
            for item in items
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                item = futures[future]
                logger.exception("Unexpected error processing roadmap item %s", item.id)
