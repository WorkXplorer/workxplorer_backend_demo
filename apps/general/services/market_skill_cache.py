from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.general.models import DomainMarketSkill
from apps.general.services.hh_aliases import filter_relevant_hh_vacancies, tokenize_market_text, VACANCY_TITLE_STOPWORDS
from apps.general.services.hh_client import collect_hh_api_vacancies
from apps.skills.localization import (
    canonical_market_skill_key,
    clean_market_skill_name,
    clean_text,
    normalized_key,
    unique_items,
)


DEFAULT_HH_MARKET_SKILL_MAX_AGE_DAYS = 60
DEFAULT_HH_MARKET_SKILL_SAVE_LIMIT = 40
DEFAULT_HH_MARKET_EMPTY_MAX_AGE_HOURS = 6
DEFAULT_HH_MARKET_LIVE_DETAIL_LIMIT = 10
DEFAULT_HH_MARKET_LIVE_QUERY_LIMIT = 2
DEFAULT_MIN_MISSING_SKILLS = 2
DEFAULT_MAX_MISSING_SKILLS = 7
MARKET_SKILL_EMPTY_MARKER = "__no_market_skills__"


def get_market_skill_max_age_days():
    value = getattr(
        settings,
        "HH_MARKET_SKILL_MAX_AGE_DAYS",
        getattr(
            settings,
            "HH_MARKET_SNAPSHOT_MAX_AGE_DAYS",
            DEFAULT_HH_MARKET_SKILL_MAX_AGE_DAYS,
        ),
    )
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_HH_MARKET_SKILL_MAX_AGE_DAYS


def get_market_skill_save_limit():
    value = getattr(
        settings,
        "HH_MARKET_SKILL_SAVE_LIMIT",
        DEFAULT_HH_MARKET_SKILL_SAVE_LIMIT,
    )
    try:
        return max(int(value), DEFAULT_MIN_MISSING_SKILLS)
    except (TypeError, ValueError):
        return DEFAULT_HH_MARKET_SKILL_SAVE_LIMIT


def get_market_empty_max_age_hours():
    value = getattr(
        settings,
        "HH_MARKET_EMPTY_MAX_AGE_HOURS",
        DEFAULT_HH_MARKET_EMPTY_MAX_AGE_HOURS,
    )
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_HH_MARKET_EMPTY_MAX_AGE_HOURS


def get_market_live_detail_limit():
    value = getattr(
        settings,
        "HH_MARKET_LIVE_DETAIL_LIMIT",
        DEFAULT_HH_MARKET_LIVE_DETAIL_LIMIT,
    )
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_HH_MARKET_LIVE_DETAIL_LIMIT


def get_market_live_query_limit():
    value = getattr(
        settings,
        "HH_MARKET_LIVE_QUERY_LIMIT",
        DEFAULT_HH_MARKET_LIVE_QUERY_LIMIT,
    )
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_HH_MARKET_LIVE_QUERY_LIMIT


def market_skill_expires_at(fetched_at=None):
    return (fetched_at or timezone.now()) + timedelta(
        days=get_market_skill_max_age_days()
    )


def empty_market_skill_expires_at(fetched_at=None):
    return (fetched_at or timezone.now()) + timedelta(
        hours=get_market_empty_max_age_hours()
    )


def domain_market_skill_scope(domain, query):
    query = clean_text(query)
    domain_name = clean_text(domain.name if domain else "")
    if domain and normalized_key(query) == normalized_key(domain_name):
        return f"domain:{domain.id}", domain
    return f"query:{normalized_key(query)}", None


def is_market_skill_scope_duplicate(skill_key, *, query="", domain=None):
    if not skill_key:
        return True

    scope_keys = {canonical_market_skill_key(query)}
    if domain:
        scope_keys.add(canonical_market_skill_key(domain.name))
    return skill_key in {key for key in scope_keys if key}


def aggregate_market_skill_items(vacancies, vacancy_index=0, aggregate=True):
    selected_vacancies = vacancies
    if not aggregate:
        selected_vacancies = (
            [vacancies[vacancy_index]]
            if vacancy_index < len(vacancies)
            else []
        )

    skill_map = {}
    for vacancy in selected_vacancies:
        vacancy_skill_keys = set()
        for vacancy_skill in vacancy.get("key_skills") or []:
            skill_name = clean_market_skill_name(vacancy_skill)
            key = canonical_market_skill_key(skill_name)
            if not key or key in vacancy_skill_keys:
                continue
            vacancy_skill_keys.add(key)
            item = skill_map.setdefault(
                key,
                {
                    "skill_name": skill_name,
                    "normalized_skill_name": key,
                    "local_skill": None,
                    "vacancy_count": 0,
                },
            )
            item["vacancy_count"] += 1

    return sorted(
        skill_map.values(),
        key=lambda item: (-item["vacancy_count"], item["skill_name"].lower()),
    )


def market_skill_rows_to_items(rows):
    return [
        {
            "skill_name": row.skill_name,
            "normalized_skill_name": row.normalized_skill_name,
            "local_skill": None,
            "vacancy_count": row.vacancy_count,
        }
        for row in rows
        if row.normalized_skill_name != MARKET_SKILL_EMPTY_MARKER
    ]


def get_fresh_domain_market_skills_for_queries(
    *,
    queries,
    area_id="97",
    domain=None,
    include_empty_markers=False,
):
    scoped_queries = []
    for query in unique_items(queries):
        scope_key, _ = domain_market_skill_scope(domain, query)
        if scope_key:
            scoped_queries.append((scope_key, clean_text(query)))
    if not scoped_queries:
        return [], ""

    scope_keys = [scope_key for scope_key, _ in scoped_queries]
    now = timezone.now()
    rows = list(
        DomainMarketSkill.objects.filter(
            source="hh",
            area_id=clean_text(area_id) or "97",
            scope_key__in=scope_keys,
            is_active=True,
            expires_at__gte=now,
        )
        .order_by("scope_key", "-vacancy_count", "skill_name")
    )
    rows_by_scope = {}
    for row in rows:
        rows_by_scope.setdefault(row.scope_key, []).append(row)

    empty_cutoff = now - timedelta(hours=get_market_empty_max_age_hours())
    empty_scope_rows = None
    empty_scope_query = ""
    for scope_key, query in scoped_queries:
        scope_rows = rows_by_scope.get(scope_key)
        if not scope_rows:
            continue
        has_market_skills = any(
            row.normalized_skill_name != MARKET_SKILL_EMPTY_MARKER
            for row in scope_rows
        )
        if has_market_skills:
            return scope_rows, query
        fresh_empty_rows = [
            row
            for row in scope_rows
            if row.normalized_skill_name == MARKET_SKILL_EMPTY_MARKER
            and row.last_seen_at >= empty_cutoff
        ]
        if include_empty_markers and fresh_empty_rows and empty_scope_rows is None:
            empty_scope_rows = fresh_empty_rows
            empty_scope_query = query

    if empty_scope_rows:
        return empty_scope_rows, empty_scope_query
    return [], ""


def upsert_domain_market_skills(
    *,
    query,
    vacancies,
    area_id="97",
    language="uz",
    domain=None,
    filter_query="",
    write_empty_marker=True,
):
    filter_query = clean_text(filter_query)
    selected_vacancies = (
        filter_relevant_hh_vacancies(vacancies, filter_query)
        if filter_query
        else vacancies
    )
    market_skills = aggregate_market_skill_items(selected_vacancies)
    scope_key, scoped_domain = domain_market_skill_scope(domain, query)
    normalized_query = normalized_key(query)
    area_id = clean_text(area_id) or "97"
    now = timezone.now()
    expires_at = market_skill_expires_at(now)
    active_items = {}
    save_limit = get_market_skill_save_limit()

    for item in market_skills:
        skill_name = clean_text(item["skill_name"])
        normalized_skill_name = item["normalized_skill_name"]
        if not skill_name or not normalized_skill_name:
            continue
        if is_market_skill_scope_duplicate(
            normalized_skill_name,
            query=query,
            domain=scoped_domain or domain,
        ):
            continue

        active_items[normalized_skill_name] = {
            "skill_name": skill_name,
            "vacancy_count": item["vacancy_count"],
        }
        if len(active_items) >= save_limit:
            break

    active_keys = list(active_items)
    if not active_keys:
        if not write_empty_marker:
            return [], len(selected_vacancies)

        marker_defaults = {
            "domain": scoped_domain,
            "query": clean_text(query),
            "normalized_query": normalized_query,
            "language": language or "uz",
            "skill_name": MARKET_SKILL_EMPTY_MARKER,
            "vacancy_count": len(selected_vacancies),
            "is_active": True,
            "last_seen_at": now,
            "expires_at": empty_market_skill_expires_at(now),
        }
        DomainMarketSkill.objects.update_or_create(
            source="hh",
            area_id=area_id,
            scope_key=scope_key,
            normalized_skill_name=MARKET_SKILL_EMPTY_MARKER,
            defaults=marker_defaults,
        )
        DomainMarketSkill.objects.filter(
            source="hh",
            area_id=area_id,
            scope_key=scope_key,
            is_active=True,
        ).exclude(normalized_skill_name=MARKET_SKILL_EMPTY_MARKER).update(
            is_active=False,
            expires_at=now,
            last_seen_at=now,
        )
        return [], len(selected_vacancies)

    existing_rows = {
        row.normalized_skill_name: row
        for row in DomainMarketSkill.objects.filter(
            source="hh",
            area_id=area_id,
            scope_key=scope_key,
            normalized_skill_name__in=active_keys,
        )
    }

    create_rows = []
    update_rows = []
    query_value = clean_text(query)
    language_value = language or "uz"
    for normalized_skill_name, item in active_items.items():
        row = existing_rows.get(normalized_skill_name)
        if row is None:
            create_rows.append(
                DomainMarketSkill(
                    source="hh",
                    area_id=area_id,
                    scope_key=scope_key,
                    normalized_skill_name=normalized_skill_name,
                    domain=scoped_domain,
                    query=query_value,
                    normalized_query=normalized_query,
                    language=language_value,
                    skill_name=item["skill_name"],
                    vacancy_count=item["vacancy_count"],
                    is_active=True,
                    first_seen_at=now,
                    last_seen_at=now,
                    expires_at=expires_at,
                )
            )
            continue

        row.domain = scoped_domain
        row.query = query_value
        row.normalized_query = normalized_query
        row.language = language_value
        row.skill_name = item["skill_name"]
        row.vacancy_count = item["vacancy_count"]
        row.is_active = True
        row.last_seen_at = now
        row.expires_at = expires_at
        row.updated_at = now
        update_rows.append(row)

    if create_rows:
        DomainMarketSkill.objects.bulk_create(create_rows)
    if update_rows:
        DomainMarketSkill.objects.bulk_update(
            update_rows,
            [
                "domain",
                "query",
                "normalized_query",
                "language",
                "skill_name",
                "vacancy_count",
                "is_active",
                "last_seen_at",
                "expires_at",
                "updated_at",
            ],
        )

    stale_queryset = DomainMarketSkill.objects.filter(
        source="hh",
        area_id=area_id,
        scope_key=scope_key,
        is_active=True,
    )
    if active_keys:
        stale_queryset = stale_queryset.exclude(normalized_skill_name__in=active_keys)
    stale_queryset.update(is_active=False, expires_at=now, last_seen_at=now)

    rows = sorted(
        [*create_rows, *update_rows],
        key=lambda row: (-row.vacancy_count, row.skill_name.lower()),
    )
    return rows, len(selected_vacancies)


def collect_hh_market_skills_with_cache(
    *,
    query,
    area_id="97",
    max_pages=2,
    per_page=30,
    language="uz",
    domain=None,
    prefer_cache=True,
    refresh_cache=False,
    query_variants=None,
    cache_query_variants=None,
    aggregate_mode=True,
    max_details=None,
    live_query_limit=None,
    filter_query="",
):
    queries = unique_items(query_variants or [query])
    if prefer_cache and not refresh_cache:
        cache_variants = (
            cache_query_variants
            if cache_query_variants is not None
            else query_variants
        )
        cache_queries = unique_items(cache_variants or [query])
        rows, cached_query = get_fresh_domain_market_skills_for_queries(
            queries=cache_queries,
            area_id=area_id,
            domain=domain,
        )
        if rows:
            vacancy_count = max((row.vacancy_count for row in rows), default=0)
            return market_skill_rows_to_items(rows), True, cached_query, vacancy_count

    last_market_skills = []
    last_vacancy_count = 0
    last_live_query = ""
    last_vacancies = []
    last_effective_filter_query = ""
    live_queries = queries[: live_query_limit or len(queries)]
    for live_query in live_queries:
        vacancies = collect_hh_api_vacancies(
            query=live_query,
            area_id=area_id,
            max_pages=max_pages,
            per_page=per_page,
            max_details=max_details,
        )
        if filter_query and aggregate_mode:
            fq_tokens = set(tokenize_market_text(filter_query)) - VACANCY_TITLE_STOPWORDS
            lq_tokens = set(tokenize_market_text(live_query))
            effective_filter_query = filter_query if (fq_tokens & lq_tokens) else live_query
        elif aggregate_mode:
            effective_filter_query = live_query
        else:
            effective_filter_query = ""
        rows, vacancy_count = upsert_domain_market_skills(
            query=live_query,
            vacancies=vacancies,
            area_id=area_id,
            language=language,
            domain=domain,
            filter_query=effective_filter_query,
            write_empty_marker=False,
        )
        market_skills = market_skill_rows_to_items(rows)
        last_market_skills = market_skills
        last_vacancy_count = vacancy_count
        last_live_query = live_query
        last_vacancies = vacancies
        last_effective_filter_query = effective_filter_query
        if market_skills:
            return market_skills, False, live_query, vacancy_count

    if last_live_query:
        rows, last_vacancy_count = upsert_domain_market_skills(
            query=last_live_query,
            vacancies=last_vacancies,
            area_id=area_id,
            language=language,
            domain=domain,
            filter_query=last_effective_filter_query,
            write_empty_marker=True,
        )
        last_market_skills = market_skill_rows_to_items(rows)

    return last_market_skills, False, last_live_query, last_vacancy_count
