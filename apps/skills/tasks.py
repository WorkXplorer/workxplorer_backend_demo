import logging

import django_rq

logger = logging.getLogger(__name__)


def validate_passive_skills_task():
    """
    Daily job: run AI validation over every pending (is_active=False) skill.

    Approved skills are activated and translated into all three languages;
    rejected and duplicate skills are deleted.

    Scheduled to run once a day at 03:00 Asia/Tashkent — see
    ``apps.skills.services.scheduler``.
    """
    from apps.ai.services.groq_client import GroqClient
    from apps.ai.services.skill_validator import validate_passive_skills

    providers = (("groq", GroqClient),)
    last_error = None
    for name, client_cls in providers:
        try:
            result = validate_passive_skills(client_cls())
            logger.info(
                "Passive skill validation via %s complete: %s",
                name,
                result.get("message"),
            )
            return result
        except Exception as exc:  # noqa: BLE001 — try the next provider
            last_error = exc
            logger.warning("Passive skill validation via %s failed: %s", name, exc)

    logger.error(
        "Passive skill validation failed on all AI providers: %s", last_error
    )
    raise RuntimeError(
        f"Skill validation failed on all AI providers: {last_error}"
    )


def generate_learning_materials_task(roadmap_id, ai_model="groq", language="en"):
    from apps.skills.services.learning_materials import generate_learning_materials_for_roadmap
    from apps.student_analytics.models import SkillRoadmap
    from apps.skills.localization import user_preferred_language

    try:
        roadmap = SkillRoadmap.objects.select_related(
            "analytics__candidate"
        ).get(id=roadmap_id)

        # Always read language fresh from the candidate's current preference
        # so changing the interface language takes effect on next generation.
        try:
            language = user_preferred_language(roadmap.analytics.candidate) or language
        except Exception:
            logger.debug("Could not resolve preferred language for roadmap %s; using default", roadmap_id)

        country = ""
        try:
            country = roadmap.analytics.candidate.candidateprofile.citizenship.name or ""
        except Exception:
            logger.debug("Could not resolve country for roadmap %s; proceeding without it", roadmap_id)

        generate_learning_materials_for_roadmap(roadmap, ai_model=ai_model, language=language, country=country)
        logger.info("Learning materials generated for roadmap %s", roadmap_id)
    except SkillRoadmap.DoesNotExist:
        logger.warning("Roadmap %s not found for learning materials generation", roadmap_id)
    except Exception:
        logger.exception("Failed to generate learning materials for roadmap %s", roadmap_id)


def enqueue_learning_materials_generation(roadmap_id, ai_model="groq", language="en"):
    try:
        django_rq.get_queue("high").enqueue(
            generate_learning_materials_task,
            roadmap_id,
            ai_model,
            language,
        )
    except Exception:
        logger.exception("Failed to enqueue learning materials generation for roadmap %s", roadmap_id)


def generate_vacancy_learning_materials_task(vacancy_roadmap_id, ai_model="groq", language="en"):
    from apps.skills.services.learning_materials import generate_learning_materials_for_roadmap
    from apps.student_analytics.models import VacancySkillRoadmap
    from apps.skills.localization import user_preferred_language

    try:
        roadmap = VacancySkillRoadmap.objects.select_related(
            "application__candidate"
        ).get(id=vacancy_roadmap_id)

        # Always read language fresh from the candidate's current preference
        # so changing the interface language takes effect on next generation.
        try:
            language = user_preferred_language(roadmap.application.candidate) or language
        except Exception:
            logger.debug(
                "Could not resolve preferred language for vacancy roadmap %s; using default",
                vacancy_roadmap_id,
            )

        country = ""
        try:
            country = roadmap.application.candidate.candidateprofile.citizenship.name or ""
        except Exception:
            logger.debug(
                "Could not resolve country for vacancy roadmap %s; proceeding without it",
                vacancy_roadmap_id,
            )

        generate_learning_materials_for_roadmap(roadmap, ai_model=ai_model, language=language, country=country)
        logger.info("Learning materials generated for vacancy roadmap %s", vacancy_roadmap_id)
    except VacancySkillRoadmap.DoesNotExist:
        logger.warning(
            "Vacancy roadmap %s not found for learning materials generation", vacancy_roadmap_id
        )
    except Exception:
        logger.exception(
            "Failed to generate learning materials for vacancy roadmap %s", vacancy_roadmap_id
        )


def enqueue_vacancy_learning_materials_generation(vacancy_roadmap_id, ai_model="groq", language="en"):
    try:
        django_rq.get_queue("high").enqueue(
            generate_vacancy_learning_materials_task,
            vacancy_roadmap_id,
            ai_model,
            language,
        )
    except Exception:
        logger.exception(
            "Failed to enqueue learning materials generation for vacancy roadmap %s",
            vacancy_roadmap_id,
        )
