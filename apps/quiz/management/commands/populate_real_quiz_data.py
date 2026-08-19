"""
Management command to populate quiz data from a JSON file.

Usage:
    python manage.py populate_quiz_data --file quiz_data.json
    python manage.py populate_quiz_data --file quiz_data.json --clear

JSON schema expected:
{
  "phase1_quiz": {
    "name": {"en": "...", "uz": "...", "ru": "..."},
    "description": {"en": "...", "uz": "...", "ru": "..."},
    "questions": [
      {
        "title": {"en": "...", "uz": "...", "ru": "..."},
        "answers": [
          {
            "text": {"en": "...", "uz": "...", "ru": "..."},
            "domain_groups": ["tech", "business"],
            "point": 10
          }
        ]
      }
    ]
  },
  "domain_groups": [
    {
      "key": "tech",
      "name": {"en": "...", "uz": "...", "ru": "..."},
      "domains": ["Information Technology & Software", "Cybersecurity"],
      "career_options": [
        {
          "title": {"en": "...", "uz": "...", "ru": "..."},
          "description": {"en": "...", "uz": "...", "ru": "..."}
        }
      ],
      "phase2_quiz": {
        "name": {"en": "...", "uz": "...", "ru": "..."},
        "description": {"en": "...", "uz": "...", "ru": "..."},
        "questions": [
          {
            "title": {"en": "...", "uz": "...", "ru": "..."},
            "answers": [
              {
                "text": {"en": "...", "uz": "...", "ru": "..."},
                "career_option": "Software Developer",
                "point": 15
              }
            ]
          }
        ]
      }
    }
  ]
}
"""

import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.quiz.models import AnswerChoice, CareerOption, Question, Quiz, QuizType
from apps.domain.models import Domain


class Command(BaseCommand):
    help = "Populate quiz data from a JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="quiz_data.json",
            help="Path to the JSON data file (default: quiz_data.json)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing quiz data before loading",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = options["file"]
        if not os.path.isabs(file_path):
            # Resolve relative to manage.py directory
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
            file_path = os.path.join(base_dir, file_path)

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if options["clear"]:
            self._clear_data()

        # Step 1: Build domain group → Domain objects mapping
        self.stdout.write("Loading domains from DB...")
        domain_group_map = self._build_domain_group_map(data["domain_groups"])

        # Step 2: Build career options (needed before phase 2 questions)
        self.stdout.write("Creating career options...")
        career_option_map = self._create_career_options(data["domain_groups"])

        # Step 3: Phase 1 quiz
        self.stdout.write("Creating Phase 1 quiz...")
        self._create_phase1_quiz(data["phase1_quiz"], domain_group_map)

        # Step 4: Phase 2 quizzes (one per domain group)
        self.stdout.write("Creating Phase 2 quizzes...")
        self._create_phase2_quizzes(data["domain_groups"], domain_group_map, career_option_map)

        self.stdout.write(self.style.SUCCESS("\n✅ Quiz data loaded successfully!"))
        self._print_summary()

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_data(self):
        self.stdout.write(self.style.WARNING("Clearing existing quiz data..."))
        AnswerChoice.objects.all().delete()
        Question.objects.all().delete()
        Quiz.objects.all().delete()
        QuizType.objects.all().delete()
        CareerOption.objects.all().delete()
        self.stdout.write(self.style.WARNING("Cleared."))

    # ------------------------------------------------------------------
    # Domain group map: group_key → list of Domain objects
    # ------------------------------------------------------------------

    def _build_domain_group_map(self, domain_groups_data):
        """
        Returns { "tech": [Domain, Domain, ...], "business": [...], ... }
        Fetches domains from DB by name_en. Warns if not found.
        """
        group_map = {}
        for group in domain_groups_data:
            key = group["key"]
            domains = []
            for domain_name in group["domains"]:
                try:
                    domain = Domain.objects.get(name_en=domain_name)
                    domains.append(domain)
                except Domain.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠ Domain not found in DB: '{domain_name}' (group: {key})"
                        )
                    )
            group_map[key] = domains
            self.stdout.write(f"  Group '{key}': {len(domains)} domains loaded")
        return group_map

    # ------------------------------------------------------------------
    # Career options
    # ------------------------------------------------------------------

    def _create_career_options(self, domain_groups_data):
        """
        Returns { "Software Developer": CareerOption, ... }
        Keyed by English title.
        """
        career_map = {}
        for group in domain_groups_data:
            for co_data in group.get("career_options", []):
                title_en = co_data["title"]["en"]
                career, created = CareerOption.objects.get_or_create(
                    title_en=title_en,
                    defaults={
                        "title":          title_en,
                        "title_en":       title_en,
                        "title_uz":       co_data["title"].get("uz", title_en),
                        "title_ru":       co_data["title"].get("ru", title_en),
                        "description":    co_data["description"].get("en", ""),
                        "description_en": co_data["description"].get("en", ""),
                        "description_uz": co_data["description"].get("uz", ""),
                        "description_ru": co_data["description"].get("ru", ""),
                    },
                )
                if not created:
                    career.title_uz       = co_data["title"].get("uz", title_en)
                    career.title_ru       = co_data["title"].get("ru", title_en)
                    career.description_en = co_data["description"].get("en", "")
                    career.description_uz = co_data["description"].get("uz", "")
                    career.description_ru = co_data["description"].get("ru", "")
                    career.save()

                career_map[title_en] = career
                status = "created" if created else "updated"
                self.stdout.write(f"  CareerOption '{title_en}' {status}")

        return career_map

    # ------------------------------------------------------------------
    # Phase 1
    # ------------------------------------------------------------------

    def _create_phase1_quiz(self, phase1_data, domain_group_map):
        """
        Creates a single QuizType + Quiz with no domain (domain discovery).
        Each answer maps to 1-2 domain groups via M2M domains.
        """
        quiz_type, _ = QuizType.objects.get_or_create(
            name_en="Domain Discovery",
            defaults={
                "name":           phase1_data["name"]["en"],
                "name_en":        phase1_data["name"]["en"],
                "name_uz":        phase1_data["name"].get("uz", ""),
                "name_ru":        phase1_data["name"].get("ru", ""),
                "description":    phase1_data["description"]["en"],
                "description_en": phase1_data["description"]["en"],
                "description_uz": phase1_data["description"].get("uz", ""),
                "description_ru": phase1_data["description"].get("ru", ""),
                "is_active": True,
                "domain": None,
            },
        )

        quiz, _ = Quiz.objects.get_or_create(
            name_en=phase1_data["name"]["en"],
            quiz_type=quiz_type,
            defaults={
                "name":           phase1_data["name"]["en"],
                "name_en":        phase1_data["name"]["en"],
                "name_uz":        phase1_data["name"].get("uz", ""),
                "name_ru":        phase1_data["name"].get("ru", ""),
                "description":    phase1_data["description"]["en"],
                "description_en": phase1_data["description"]["en"],
                "description_uz": phase1_data["description"].get("uz", ""),
                "description_ru": phase1_data["description"].get("ru", ""),
                "is_active": True,
            },
        )

        for q_data in phase1_data["questions"]:
            question, _ = Question.objects.get_or_create(
                quiz=quiz,
                title_en=q_data["title"]["en"],
                defaults={
                    "title":    q_data["title"]["en"],
                    "title_en": q_data["title"]["en"],
                    "title_uz": q_data["title"].get("uz", ""),
                    "title_ru": q_data["title"].get("ru", ""),
                    "is_active": True,
                },
            )

            for a_data in q_data["answers"]:
                answer, _ = AnswerChoice.objects.get_or_create(
                    question=question,
                    text_en=a_data["text"]["en"],
                    defaults={
                        "text":    a_data["text"]["en"],
                        "text_en": a_data["text"]["en"],
                        "text_uz": a_data["text"].get("uz", ""),
                        "text_ru": a_data["text"].get("ru", ""),
                        "point":   a_data.get("point", 10),
                    },
                )

                # Map answer to all domain objects in the specified groups via M2M
                for group_key in a_data.get("domain_groups", []):
                    for domain_obj in domain_group_map.get(group_key, []):
                        answer.domains.add(domain_obj)

        self.stdout.write(
            f"  Phase 1 quiz: '{quiz.name}' — {len(phase1_data['questions'])} questions"
        )

    # ------------------------------------------------------------------
    # Phase 2
    # ------------------------------------------------------------------

    def _create_phase2_quizzes(self, domain_groups_data, domain_group_map, career_option_map):
        """
        Creates one QuizType + Quiz per domain group.
        QuizType.domain is set to the first domain in the group (used by determine_domain view).
        Each answer links to exactly one CareerOption.
        """
        for group in domain_groups_data:
            key = group["key"]
            phase2 = group["phase2_quiz"]
            group_domains = domain_group_map.get(key, [])

            # The determine_domain view filters by quiz_type__domain_id,
            # so we attach ALL group domains to the quiz type by setting
            # each domain's quiz_type FK. Since QuizType.domain is a single FK,
            # we create one QuizType per domain in the group and link them all
            # to the same Quiz — OR we simply use the first domain as the FK
            # and rely on the M2M answer.domains for scoring accuracy.
            # Choice: use first domain as FK (simpler, consistent with existing logic).
            primary_domain = group_domains[0] if group_domains else None

            quiz_type, _ = QuizType.objects.get_or_create(
                name_en=phase2["name"]["en"],
                defaults={
                    "name":           phase2["name"]["en"],
                    "name_en":        phase2["name"]["en"],
                    "name_uz":        phase2["name"].get("uz", ""),
                    "name_ru":        phase2["name"].get("ru", ""),
                    "description":    phase2["description"]["en"],
                    "description_en": phase2["description"]["en"],
                    "description_uz": phase2["description"].get("uz", ""),
                    "description_ru": phase2["description"].get("ru", ""),
                    "is_active": True,
                    "domain":   primary_domain,
                },
            )

            quiz, _ = Quiz.objects.get_or_create(
                name_en=phase2["name"]["en"],
                quiz_type=quiz_type,
                defaults={
                    "name":           phase2["name"]["en"],
                    "name_en":        phase2["name"]["en"],
                    "name_uz":        phase2["name"].get("uz", ""),
                    "name_ru":        phase2["name"].get("ru", ""),
                    "description":    phase2["description"]["en"],
                    "description_en": phase2["description"]["en"],
                    "description_uz": phase2["description"].get("uz", ""),
                    "description_ru": phase2["description"].get("ru", ""),
                    "is_active": True,
                },
            )

            for q_data in phase2["questions"]:
                question, _ = Question.objects.get_or_create(
                    quiz=quiz,
                    title_en=q_data["title"]["en"],
                    defaults={
                        "title":    q_data["title"]["en"],
                        "title_en": q_data["title"]["en"],
                        "title_uz": q_data["title"].get("uz", ""),
                        "title_ru": q_data["title"].get("ru", ""),
                        "is_active": True,
                    },
                )

                for a_data in q_data["answers"]:
                    career_title = a_data.get("career_option")
                    career_obj = career_option_map.get(career_title) if career_title else None

                    if career_title and not career_obj:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ⚠ CareerOption not found: '{career_title}' "
                                f"(question: {q_data['title']['en'][:50]})"
                            )
                        )

                    AnswerChoice.objects.get_or_create(
                        question=question,
                        text_en=a_data["text"]["en"],
                        defaults={
                            "text":          a_data["text"]["en"],
                            "text_en":       a_data["text"]["en"],
                            "text_uz":       a_data["text"].get("uz", ""),
                            "text_ru":       a_data["text"].get("ru", ""),
                            "point":         a_data.get("point", 10),
                            "career_option": career_obj,
                        },
                    )

            self.stdout.write(
                f"  Phase 2 '{key}': '{quiz.name}' — "
                f"{len(phase2['questions'])} questions, "
                f"{len(group.get('career_options', []))} career options"
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(self):
        self.stdout.write("\n📊 Summary:")
        self.stdout.write(f"  Quiz Types:     {QuizType.objects.count()}")
        self.stdout.write(f"  Quizzes:        {Quiz.objects.count()}")
        self.stdout.write(f"  Questions:      {Question.objects.count()}")
        self.stdout.write(f"  Answer Choices: {AnswerChoice.objects.count()}")
        self.stdout.write(f"  Career Options: {CareerOption.objects.count()}")
        self.stdout.write("\n📝 Quizzes:")
        for quiz in Quiz.objects.select_related("quiz_type").all():
            q_count = quiz.questions.filter(is_active=True).count()
            self.stdout.write(f"  [{quiz.id}] {quiz.name} — {q_count} questions")