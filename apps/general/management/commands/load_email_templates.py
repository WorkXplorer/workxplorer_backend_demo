"""
Management command to load email templates from HTML files into the database.
"""
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile

from apps.general.models import EmailTemplate


class Command(BaseCommand):
    help = "Load email templates from HTML files into the database"

    def handle(self, *args, **options):
        """Load email templates from email-templates directory."""
        
        # Get the project root directory
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
        email_templates_dir = base_dir / "email-templates"

        if not email_templates_dir.exists():
            self.stdout.write(
                self.style.ERROR(f"Email templates directory not found: {email_templates_dir}")
            )
            return

        # Template definitions
        templates = {
            "applications-summary-uz.html": {
                "template_type": "applications-summary",
                "name": "applications-summary",
                "language": "uz",
                "subject": "WorkXplorer - Yangi arizalar xulosasi | {{ period_hours }} soat",
            },
            "applications-summary-ru.html": {
                "template_type": "applications-summary",
                "name": "applications-summary",
                "language": "ru",
                "subject": "WorkXplorer - Сводка новых откликов | {{ period_hours }} часов",
            },
            "applications-summary-en.html": {
                "template_type": "applications-summary",
                "name": "applications-summary",
                "language": "en",
                "subject": "WorkXplorer - New Applications Summary | {{ period_hours }} hours",
            },
            # Quiz result emails (case 1 - new anonymous user: career cards + register CTA)
            "quiz-result-uz.html": {
                "template_type": "quiz-result",
                "name": "quiz-result",
                "language": "uz",
                "subject": "WorkXplorer - Karyera testi natijalari",
            },
            "quiz-result-ru.html": {
                "template_type": "quiz-result",
                "name": "quiz-result",
                "language": "ru",
                "subject": "WorkXplorer - Результаты карьерного теста",
            },
            "quiz-result-en.html": {
                "template_type": "quiz-result",
                "name": "quiz-result",
                "language": "en",
                "subject": "WorkXplorer - Your Career Quiz Results",
            },
        }

        loaded_count = 0
        skipped_count = 0

        for filename, template_config in templates.items():
            template_path = email_templates_dir / template_config["language"] / filename

            if not template_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"Template file not found: {template_path}")
                )
                skipped_count += 1
                continue

            try:
                # Read HTML content
                with open(template_path, "r", encoding="utf-8") as f:
                    html_content = f.read()

                # Check if template already exists
                existing = EmailTemplate.objects.filter(
                    template_type=template_config["template_type"],
                    language=template_config["language"],
                ).first()

                if existing:
                    # Update existing template
                    existing.subject = template_config["subject"]
                    existing.body.save(
                        filename,
                        ContentFile(html_content.encode("utf-8")),
                        save=False,
                    )
                    existing.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated template: {template_config['name']} ({template_config['language']})"
                        )
                    )
                else:
                    # Create new template
                    template = EmailTemplate(
                        template_type=template_config["template_type"],
                        name=template_config["name"],
                        language=template_config["language"],
                        subject=template_config["subject"],
                    )
                    template.body.save(
                        filename,
                        ContentFile(html_content.encode("utf-8")),
                        save=False,
                    )
                    template.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Loaded template: {template_config['name']} ({template_config['language']})"
                        )
                    )

                loaded_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to load template {filename}: {str(e)}"
                    )
                )
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSummary: {loaded_count} templates loaded, {skipped_count} skipped"
            )
        )
