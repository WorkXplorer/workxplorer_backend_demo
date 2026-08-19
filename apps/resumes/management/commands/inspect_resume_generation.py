"""
Run resume generation against a source text and show every stage of it.

Diagnosing a thin skills list from the outside means reading worker logs and
guessing which stage dropped what. This runs the real pipeline — same prompt,
same model call, same mapper — and prints what the model saw, what it proposed,
and what survived, without saving a resume.

    python manage.py inspect_resume_generation --file source.txt
    python manage.py inspect_resume_generation --file source.txt --seed
    python manage.py inspect_resume_generation --text "Системный аналитик..."

``--seed`` fills a nearly-empty development database with the reference data
generation depends on: skills with translations and categories, domains, and
languages. A result means little without it — skill matching is only as good as
the table it matches against, an empty domain table makes the model invent a
domain, and languages cannot resolve to rows that do not exist.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.resumes.services.resume_generation import (
    generate_resume,
    map_ai_response_to_database,
    verify_evidence_quote,
)
from apps.domain.models import Domain
from apps.resumes.services.skill_resolution import is_creatable_skill_name

# A slice of a real vocabulary: English canonical names, Russian translations,
# and categories from more than one profession — enough for the prompt to be
# shaped like production's, including the cross-profession traps.
SEED_SKILLS = [
    ("Software Engineering", "Python", "Python"),
    ("Software Engineering", "Django", "Django"),
    ("Software Engineering", "PostgreSQL", "PostgreSQL"),
    ("Software Engineering", "REST API", "REST API"),
    ("Business Analysis", "System Analysis", "Системный анализ"),
    ("Business Analysis", "Business Analysis", "Бизнес-анализ"),
    ("Business Analysis", "Requirements Gathering", "Сбор требований"),
    ("Business Analysis", "Documentation", "Документация"),
    ("Business Analysis", "Process Modeling", "Моделирование процессов"),
    ("Business Analysis", "Stakeholder Management", "Управление стейкхолдерами"),
    ("Project Management", "Project Management", "Управление проектами"),
    ("Project Management", "Agile", "Agile"),
    ("Project Management", "Scrum", "Scrum"),
    ("Finance", "Financial Modeling", "Финансовое моделирование"),
    ("Finance", "Payment Systems", "Платёжные системы"),
    ("Healthcare", "Medical Documentation", "Медицинская документация"),
    ("Healthcare", "Patient Care", "Уход за пациентами"),
    ("Agriculture", "Soil Analysis", "Анализ почвы"),
]


SEED_DOMAINS = [
    "Information Technology",
    "Business Analysis",
    "Finance",
    "Healthcare",
]

SEED_LANGUAGES = [("English", "en"), ("Russian", "ru"), ("Uzbek", "uz")]


class Command(BaseCommand):
    help = "Run resume generation on a source text and report every stage."

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--file", help="Path to a file holding the source resume text.")
        source.add_argument("--text", help="Source resume text given inline.")
        parser.add_argument(
            "--seed", "--seed-skills",
            dest="seed",
            action="store_true",
            help="Create realistic reference data first (development databases).",
        )
        parser.add_argument(
            "--candidate",
            help=(
                "Email of the candidate to attribute created skills to. Without "
                "it nothing is created; the report lists what would have been."
            ),
        )

    def handle(self, *args, **options):
        if options["seed"]:
            self._seed_reference_data()

        source_text = self._read_source(options)
        created_by = self._resolve_candidate(options.get("candidate"))

        self._heading("Calling the model")
        ai_response = generate_resume(source_type="prompt", content=source_text)
        resume = ai_response.get("resume", {})

        mentions = ai_response.get("skill_mentions") or []
        self._heading(f"Skills the model found ({len(mentions)})")
        for mention in mentions:
            name = mention.get("skill")
            quote = mention.get("quote") or ""
            verified = verify_evidence_quote(quote, source_text)
            mark = self.style.SUCCESS("quoted") if verified else self.style.WARNING("BAD QUOTE")
            self.stdout.write(f"  · {name} [{mark}] {quote[:70]}")

        mapped = map_ai_response_to_database(
            ai_response, source_text=source_text, created_by=created_by,
        )
        kept = mapped["resume"]["skills_data"]
        metadata = mapped["mapping_metadata"]

        self._heading(f"Skills kept ({len(kept)})")
        for skill in kept:
            self.stdout.write(
                f"  · {skill['skill_name']} "
                f"({skill['proficiency_level']}, {skill['minimum_years']}y)"
            )

        self._heading("Dropped, and why")
        for bucket in (
            "skills_unmatched", "skills_hallucinated", "skills_over_limit",
            "skills_created",
        ):
            entries = metadata.get(bucket) or []
            if entries:
                self.stdout.write(f"  {bucket}: {entries}")

        if not created_by:
            would_create = [
                name for name in (metadata.get("skills_unmatched") or [])
                if is_creatable_skill_name(name)
            ]
            if would_create:
                self.stdout.write(
                    f"  would be created with --candidate: {would_create}"
                )

        self._heading("Summary")
        self.stdout.write(f"  {mapped['resume'].get('description') or '(empty)'}")

        languages = mapped["resume"].get("language_certificates_data") or []
        self._heading(f"Languages ({len(languages)})")
        for language in languages:
            self.stdout.write(f"  · {language['language_name']} — {language['level']}")
        for unmatched in metadata.get("languages_unmatched") or []:
            self.stdout.write(self.style.WARNING(f"  · {unmatched} — no row in the language table"))

        self._heading("Other fields")
        self.stdout.write(f"  position: {resume.get('position')}")
        self.stdout.write(
            f"  domain:   {mapped['resume'].get('domain_name')} "
            f"(id={mapped['resume'].get('domain_id')}, {Domain.objects.count()} in table)"
        )
        self.stdout.write(f"  experiences: {len(resume.get('experiences_data') or [])}")

    def _heading(self, text):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(text))

    def _read_source(self, options):
        if options.get("text"):
            return options["text"]
        try:
            with open(options["file"], encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            raise CommandError(f"Could not read {options['file']}: {exc}") from exc

    def _resolve_candidate(self, email):
        if not email:
            return None

        from apps.authentication.models import Candidate

        candidate = Candidate.objects.filter(email=email).first()
        if not candidate:
            raise CommandError(f"No candidate with email {email}")
        return candidate

    def _seed_reference_data(self):
        from apps.languages.models import Language
        from apps.skills.models import Skill, SkillCategory

        for name in SEED_DOMAINS:
            Domain.objects.get_or_create(name=name)

        for name, code in SEED_LANGUAGES:
            if not Language.objects.filter(code=code).exists():
                Language.objects.create(name=name, code=code)

        created = 0
        for category_name, name_en, name_ru in SEED_SKILLS:
            category, _ = SkillCategory.objects.get_or_create(name=category_name)
            skill, was_created = Skill.objects.get_or_create(name=name_en)
            skill.name_en = name_en
            skill.name_ru = name_ru
            skill.is_active = True
            skill.save()
            skill.category.add(category)
            created += int(was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created} new skills, {Domain.objects.count()} domains, "
            f"{Language.objects.count()} languages."
        ))
