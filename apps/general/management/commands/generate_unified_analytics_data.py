"""
Unified Analytics Test Data Generation Command.

This command provides a unified interface for generating test data for both:
- EduPartner Analytics
- HR Analytics

It ensures that shared entities (universities, companies, domains, skills) are
consistent across both analytics systems and provides functionality to send
historical data to analytics services in chronological order.

Usage:
    # Generate all test data using unified approach
    python manage.py generate_unified_analytics_data
    
    # Generate only HR analytics data
    python manage.py generate_unified_analytics_data --hr-only
    
    # Generate only EduPartner analytics data
    python manage.py generate_unified_analytics_data --edupartner-only
    
    # Send historical data for a specific year
    python manage.py generate_unified_analytics_data --send-historical --year 2025
    
    # Clear existing data first
    python manage.py generate_unified_analytics_data --clear-existing
    
    # Generate data for a SPECIFIC COMPANY within a date range
    # This creates candidates, vacancies, resumes, applications, and views
    # only for the specified company.
    python manage.py generate_unified_analytics_data \\
        --company-id "019c2383-9a0b-73a5-b014-0ec2d96032d8" \\
        --data-start-date "2026-01-01" \\
        --data-end-date "2026-02-03" \\
        --candidates 50 \\
        --vacancies-count 10 \\
        --skip-embeddings
    
    # DELETE all data for a SPECIFIC COMPANY
    # This deletes all vacancies, applications, views, recruiters, and the company itself.
    # Note: Candidates and resumes are NOT deleted as they may be related to other companies.
    python manage.py generate_unified_analytics_data \\
        --company-id "019c2383-9a0b-73a5-b014-0ec2d96032d8" \\
        --is-delete
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Dict, List, Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.edupartners.models import EduPartner, EduPartnersType, Faculty
from apps.authentication.models import Candidate, Company, Recruiter
from apps.profiles.models import CandidateProfile, RecruiterProfile, CompanyProfile
from apps.domain.models import Domain
from apps.skills.models import Skill
from apps.vacancies.models import Vacancy, VacancySkill, VacancyView
from apps.resumes.models import Resume, ResumeSkill
from apps.applications.models import JobApplication
from apps.applications.models.choices import ApplicationStatus

# Import shared configuration
from utils.shared_test_data_config import (
    DOMAIN_NAMES,
    SKILL_NAMES,
    REAL_COMPANIES,
    IMAGINARY_COMPANIES,
    REAL_UNIVERSITIES,
    IMAGINARY_UNIVERSITIES,
    DefaultConfig,
    get_data_start_date,
    get_data_end_date,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """
    Unified analytics test data generation command.
    Generates consistent test data for both EduPartner and HR analytics services.
    Also supports sending historical data to analytics services in chronological order.
    """

    def add_arguments(self, parser):
        # Data generation options
        parser.add_argument(
            "--hr-only",
            action="store_true",
            help="Generate only HR analytics test data",
        )
        parser.add_argument(
            "--edupartner-only",
            action="store_true",
            help="Generate only EduPartner analytics test data",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing test data before generating new data",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating data",
        )

        # Historical data sending options
        parser.add_argument(
            "--send-historical",
            action="store_true",
            help="Send historical data to analytics services instead of generating",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Year for historical data sending (e.g., 2025). Required with --send-historical",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            default=None,
            help="Start date for historical data sending (YYYY-MM-DD format)",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default=None,
            help="End date for historical data sending (YYYY-MM-DD format)",
        )

        # Data amount configuration
        parser.add_argument(
            "--universities",
            type=int,
            default=DefaultConfig.EDUPARTNER_UNIVERSITIES,
            help=f"Number of universities for EduPartner (default: {DefaultConfig.EDUPARTNER_UNIVERSITIES})",
        )
        parser.add_argument(
            "--students-per-university",
            type=int,
            default=DefaultConfig.EDUPARTNER_STUDENTS_PER_UNIVERSITY,
            help=f"Students per university for EduPartner (default: {DefaultConfig.EDUPARTNER_STUDENTS_PER_UNIVERSITY})",
        )
        parser.add_argument(
            "--companies",
            type=int,
            default=DefaultConfig.HR_COMPANIES,
            help=f"Number of companies for HR analytics (default: {DefaultConfig.HR_COMPANIES})",
        )
        parser.add_argument(
            "--candidates",
            type=int,
            default=DefaultConfig.HR_CANDIDATES,
            help=f"Number of candidates for HR analytics (default: {DefaultConfig.HR_CANDIDATES})",
        )
        parser.add_argument(
            "--skip-embeddings",
            action="store_true",
            help="Skip embedding generation (faster for testing)",
        )

        # Company-specific data generation options
        parser.add_argument(
            "--company-id",
            type=str,
            default=None,
            help="UUID of the company to generate data for. When specified, generates data only for this company.",
        )
        parser.add_argument(
            "--data-start-date",
            type=str,
            default=None,
            help="Start date for data generation (YYYY-MM-DD format). Used with --company-id.",
        )
        parser.add_argument(
            "--data-end-date",
            type=str,
            default=None,
            help="End date for data generation (YYYY-MM-DD format). Used with --company-id.",
        )
        parser.add_argument(
            "--vacancies-count",
            type=int,
            default=10,
            help="Number of vacancies to create for the specific company (default: 10). Used with --company-id.",
        )
        parser.add_argument(
            "--is-delete",
            action="store_true",
            help="Delete all data related to the specified company. Must be used with --company-id.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("Unified Analytics Test Data Generation"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        # Handle company-specific data generation
        if options.get("company_id"):
            self._handle_company_specific_generation(options)
            return

        # Handle historical data sending
        if options["send_historical"]:
            self._handle_send_historical(options)
            return

        # Handle test data generation
        self._handle_data_generation(options)

    def _handle_send_historical(self, options):
        """Handle sending historical data to analytics services."""
        year = options.get("year")
        start_date_str = options.get("start_date")
        end_date_str = options.get("end_date")

        # Determine date range
        if year:
            start_date = datetime(year, 1, 1, tzinfo=dt_timezone.utc)
            end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=dt_timezone.utc)
            self.stdout.write(f"Sending historical data for year {year}")
        elif start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=dt_timezone.utc
            )
            self.stdout.write(f"Sending historical data from {start_date.date()} to {end_date.date()}")
        else:
            self.stdout.write(self.style.ERROR(
                "Please specify either --year or both --start-date and --end-date"
            ))
            return

        # Send data to both services
        hr_only = options.get("hr_only", False)
        edupartner_only = options.get("edupartner_only", False)

        if not hr_only:
            self._send_edupartner_historical_data(start_date, end_date)

        if not edupartner_only:
            self._send_hr_historical_data(start_date, end_date)

        self.stdout.write(self.style.SUCCESS("\nHistorical data sending completed!"))

    def _send_edupartner_historical_data(self, start_date: datetime, end_date: datetime):
        """Send historical EduPartner analytics data in chronological order."""
        self.stdout.write("\n" + "-" * 50)
        self.stdout.write("Sending EduPartner Historical Analytics Data")
        self.stdout.write("-" * 50)

        try:
            from apps.edupartners.services.analytics.main import EduPartnerAnalyticsService
            from apps.edupartners.tasks import _send_analytics_to_service

            # Get all active faculty IDs
            faculty_ids = EduPartnerAnalyticsService.get_faculty_ids()

            if not faculty_ids:
                self.stdout.write(self.style.WARNING("No active faculties found"))
                return

            self.stdout.write(f"Found {len(faculty_ids)} active faculties")

            # Generate date range (day by day)
            current_date = start_date
            total_days = (end_date - start_date).days + 1
            sent_count = 0
            error_count = 0

            self.stdout.write(f"Processing {total_days} days of historical data...")

            while current_date <= end_date:
                # For each day, collect and send analytics for each faculty
                for faculty_id in faculty_ids:
                    try:
                        # Collect analytics data for this faculty
                        analytics_data = EduPartnerAnalyticsService.get_faculty_analytics(faculty_id)

                        if not analytics_data:
                            continue

                        # Override timestamp with historical date
                        analytics_data["timestamp"] = current_date.isoformat()

                        # Send to external service
                        _send_analytics_to_service(analytics_data)
                        sent_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.warning(
                            f"Failed to send EduPartner analytics for faculty {faculty_id} on {current_date.date()}: {e}"
                        )

                # Progress update every 7 days
                days_processed = (current_date - start_date).days + 1
                if days_processed % 7 == 0 or current_date >= end_date:
                    self.stdout.write(
                        f"  Progress: {days_processed}/{total_days} days, "
                        f"{sent_count} sent, {error_count} errors"
                    )

                current_date += timedelta(days=1)

            self.stdout.write(self.style.SUCCESS(
                f"EduPartner historical data: {sent_count} sent, {error_count} errors"
            ))

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Import error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error sending EduPartner historical data: {e}"))

    def _send_hr_historical_data(self, start_date: datetime, end_date: datetime):
        """Send historical HR analytics data in chronological order."""
        self.stdout.write("\n" + "-" * 50)
        self.stdout.write("Sending HR Historical Analytics Data")
        self.stdout.write("-" * 50)

        try:
            from apps.general.services.analytics.main import HRAnalyticsService
            from apps.general.tasks import _send_analytics_to_service

            # Get all active company IDs
            company_ids = HRAnalyticsService.get_company_ids()

            if not company_ids:
                self.stdout.write(self.style.WARNING("No active companies found"))
                return

            self.stdout.write(f"Found {len(company_ids)} active companies")

            # Generate date range (day by day)
            # HR analytics uses period_days for analysis window
            period_days = 30  # Default analysis period

            current_date = start_date
            total_days = (end_date - start_date).days + 1
            sent_count = 0
            error_count = 0

            self.stdout.write(f"Processing {total_days} days of historical data...")

            while current_date <= end_date:
                # For each day, collect and send analytics for each company
                for company_id in company_ids:
                    try:
                        # Collect analytics data for this company with current_date as end_date
                        analytics_data = HRAnalyticsService.get_company_analytics(
                            company_id=str(company_id),
                            end_date=current_date,
                            period_days=period_days,
                        )

                        if not analytics_data:
                            continue

                        # Override timestamp with historical date
                        analytics_data["timestamp"] = current_date.isoformat()
                        analytics_data["analytics_timestamp"] = current_date.isoformat()

                        # Send to external service
                        _send_analytics_to_service(analytics_data, str(company_id))
                        sent_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.warning(
                            f"Failed to send HR analytics for company {company_id} on {current_date.date()}: {e}"
                        )

                # Progress update every 7 days
                days_processed = (current_date - start_date).days + 1
                if days_processed % 7 == 0 or current_date >= end_date:
                    self.stdout.write(
                        f"  Progress: {days_processed}/{total_days} days, "
                        f"{sent_count} sent, {error_count} errors"
                    )

                current_date += timedelta(days=1)

            self.stdout.write(self.style.SUCCESS(
                f"HR historical data: {sent_count} sent, {error_count} errors"
            ))

        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Import error: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error sending HR historical data: {e}"))

    def _handle_company_specific_generation(self, options):
        """
        Handle data generation for a specific company.
        
        This generates candidates, vacancies, resumes, applications, and views
        only for the specified company within the given date range.
        
        If --is-delete flag is set, deletes all data related to the company instead.
        """
        from utils.company_data_generator import parse_date_string

        company_id = options.get("company_id")
        is_delete = options.get("is_delete", False)
        start_date_str = options.get("data_start_date")
        end_date_str = options.get("data_end_date")
        vacancies_count = options.get("vacancies_count", 10)
        candidates_count = options.get("candidates", 50)
        skip_embeddings = options.get("skip_embeddings", False)

        # Get the company
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Company with ID {company_id} not found."))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Invalid company ID: {e}"))
            return

        # If deletion is requested, perform deletion and return
        if is_delete:
            self._delete_company_data(company)
            return

        # Validate required parameters for data generation
        if not start_date_str or not end_date_str:
            self.stdout.write(self.style.ERROR(
                "When using --company-id, you must also specify --data-start-date and --data-end-date"
            ))
            return

        # Parse dates
        try:
            start_date = parse_date_string(start_date_str)
            end_date = parse_date_string(end_date_str).replace(
                hour=23, minute=59, second=59
            )
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"Invalid date format: {e}. Use YYYY-MM-DD format."))
            return

        if start_date >= end_date:
            self.stdout.write(self.style.ERROR("Start date must be before end date."))
            return

        self.stdout.write("\n" + "-" * 50)
        self.stdout.write(f"Generating Data for Company: {company.name}")
        self.stdout.write("-" * 50)
        self.stdout.write(f"  Company ID: {company_id}")
        self.stdout.write(f"  Date Range: {start_date.date()} to {end_date.date()}")
        self.stdout.write(f"  Vacancies to create: {vacancies_count}")
        self.stdout.write(f"  Candidates to create: {candidates_count}")

        # Get or create the recruiter for this company
        recruiter = Recruiter.objects.filter(company=company).first()
        if not recruiter:
            # Create a recruiter for this company automatically
            from utils.company_data_generator import generate_phone_number

            company_email_name = company.name.lower().replace(" ", "").replace("-", "")
            recruiter_email = f"hr@{company_email_name}.uz"

            self.stdout.write(self.style.WARNING(
                f"  No recruiter found for company {company.name}. Creating one..."
            ))

            recruiter = Recruiter.objects.create(
                email=recruiter_email,
                company=company,
                is_recruiter=True,
                is_active=True,
            )

            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"{company.name} HR Manager",
                phone=generate_phone_number(),
            )

            self.stdout.write(self.style.SUCCESS(f"  Created recruiter: {recruiter_email}"))

        self.stdout.write(f"  Using recruiter: {recruiter.email}")

        # Get required base data
        domains = list(Domain.objects.all())
        skills = list(Skill.objects.all())

        if not domains:
            self.stdout.write(self.style.WARNING("No domains found. Creating default domains..."))
            domains = self._create_domains()
            domains = list(domains.values())

        if not skills:
            self.stdout.write(self.style.WARNING("No skills found. Creating default skills..."))
            skills_dict = self._create_skills()
            skills = list(skills_dict.values())

        # Get a university for candidates (use first active or None)
        university = EduPartner.objects.filter(is_active=True).first()
        faculties = list(university.faculties.all()) if university else []

        # Calculate inactive threshold (vacancies older than 30 days before end_date are inactive)
        inactive_threshold = end_date - timedelta(days=30)

        with transaction.atomic():
            # 1. Create candidates
            self.stdout.write("\n  Creating candidates...")
            candidates = self._create_company_candidates(
                count=candidates_count,
                university=university,
                faculties=faculties,
                start_date=start_date,
                end_date=end_date,
            )
            self.stdout.write(f"    Created {len(candidates)} candidates")

            # 2. Create vacancies for this company only
            self.stdout.write("\n  Creating vacancies...")
            vacancies = self._create_company_vacancies(
                company=company,
                recruiter=recruiter,
                count=vacancies_count,
                domains=domains,
                skills=skills,
                start_date=start_date,
                end_date=end_date,
                inactive_threshold=inactive_threshold,
                skip_embeddings=skip_embeddings,
            )
            self.stdout.write(f"    Created {len(vacancies)} vacancies")

            # 3. Create resumes for candidates
            self.stdout.write("\n  Creating resumes...")
            resumes = self._create_company_resumes(
                candidates=candidates,
                skills=skills,
                domains=domains,
                start_date=start_date,
                end_date=end_date,
                skip_embeddings=skip_embeddings,
            )
            self.stdout.write(f"    Created {len(resumes)} resumes")

            # 4. Create applications (candidates applying to company's vacancies)
            self.stdout.write("\n  Creating applications...")
            applications = self._create_company_applications(
                candidates=candidates,
                vacancies=vacancies,
                start_date=start_date,
                end_date=end_date,
            )
            self.stdout.write(f"    Created {len(applications)} applications")

            # 5. Create vacancy views
            self.stdout.write("\n  Creating vacancy views...")
            views = self._create_company_vacancy_views(
                candidates=candidates,
                vacancies=vacancies,
                start_date=start_date,
                end_date=end_date,
            )
            self.stdout.write(f"    Created {len(views)} vacancy views")

        # Show summary
        self._show_company_specific_summary(
            company=company,
            candidates=candidates,
            vacancies=vacancies,
            resumes=resumes,
            applications=applications,
            views=views,
            start_date=start_date,
            end_date=end_date,
        )

    def _create_company_candidates(
            self,
            count: int,
            university: Optional[EduPartner],
            faculties: List,
            start_date: datetime,
            end_date: datetime,
    ) -> List[Candidate]:
        """Create candidates for company-specific data generation."""
        import random
        from utils.company_data_generator import (
            generate_random_name,
            generate_unique_email,
            generate_phone_number,
            generate_birth_date,
        )

        candidates = []
        regions = list(CandidateProfile.RegionChoices)

        for i in range(count):
            first_name, last_name, full_name = generate_random_name()
            email = generate_unique_email(first_name, last_name, i)
            birth_date = generate_birth_date()

            # 40% chance of being affiliated with university
            assign_to_uni = university and random.random() < 0.4

            candidate = Candidate.objects.create(
                email=email,
                date_of_birth=birth_date,
                is_candidate=True,
                is_active=True,
                edupartner=university if assign_to_uni else None,
                faculty=random.choice(faculties) if assign_to_uni and faculties else None,
            )

            CandidateProfile.objects.create(
                candidate=candidate,
                full_name=full_name,
                candidate_email=email,
                region=random.choice(regions),
                phone=generate_phone_number(),
            )

            candidates.append(candidate)

        return candidates

    def _create_company_vacancies(
            self,
            company: Company,
            recruiter: Recruiter,
            count: int,
            domains: List[Domain],
            skills: List[Skill],
            start_date: datetime,
            end_date: datetime,
            inactive_threshold: datetime,
            skip_embeddings: bool,
    ) -> List[Vacancy]:
        """Create vacancies for a specific company."""
        import random
        from utils.company_data_generator import (
            generate_random_timestamp,
            get_random_language,
            generate_vacancy_data,
            select_random_skills,
            generate_skill_data,
        )

        vacancies = []

        for i in range(count):
            # Generate random timestamp within date range
            created_at = generate_random_timestamp(start_date, end_date)

            # Pick random language for content
            lang = get_random_language()

            # Generate vacancy data
            vacancy_data = generate_vacancy_data(
                language=lang,
                created_at=created_at,
                inactive_threshold=inactive_threshold,
            )

            vacancy = Vacancy(
                created_by=recruiter,
                company=company,
                domain=random.choice(domains) if domains else None,
                contact_email=f"jobs@{company.name.lower().replace(' ', '')}.uz",
                **vacancy_data,
            )
            vacancy.save()

            # Update created_at using raw SQL to bypass auto_now_add
            Vacancy.objects.filter(pk=vacancy.pk).update(
                created_at=created_at,
                updated_at=created_at + timedelta(
                    days=random.randint(0, 10),
                    hours=random.randint(0, 12)
                ),
            )
            vacancy.refresh_from_db()

            # Add random skills to vacancy
            vacancy_skills = select_random_skills(skills, min_count=3, max_count=8)
            for skill in vacancy_skills:
                skill_data = generate_skill_data()
                VacancySkill.objects.create(
                    vacancy=vacancy,
                    skill=skill,
                    **skill_data,
                )

            vacancies.append(vacancy)

        # Generate embeddings if not skipped
        if not skip_embeddings and vacancies:
            self._generate_vacancy_embeddings(vacancies)

        return vacancies

    def _create_company_resumes(
            self,
            candidates: List[Candidate],
            skills: List[Skill],
            domains: List[Domain],
            start_date: datetime,
            end_date: datetime,
            skip_embeddings: bool,
    ) -> List[Resume]:
        """Create resumes for candidates."""
        import random
        from apps.resumes.models import ResumeExperience
        from apps.resumes.models.choices import ProficiencyLevel
        from utils.company_data_generator import (
            generate_random_timestamp,
            get_random_language,
            generate_resume_data,
            generate_experience_data,
            select_random_skills,
        )

        resumes = []
        proficiency_levels = list(ProficiencyLevel)

        for candidate in candidates:
            # 85% of candidates have resumes
            if random.random() > 0.85:
                continue

            try:
                profile = CandidateProfile.objects.get(candidate=candidate)
            except CandidateProfile.DoesNotExist:
                continue

            # Pick random language for content
            lang = get_random_language()

            # Generate resume data
            resume_data = generate_resume_data(lang, profile.full_name)

            # Random creation date within range
            created_at = generate_random_timestamp(start_date, end_date)

            resume = Resume(
                candidate=candidate,
                title=resume_data["title"],
                description=resume_data["description"],
                position=resume_data["position"],
                domain=random.choice(domains) if domains else None,
                work_status=resume_data["work_status"],
                is_active=resume_data["is_active"],
                is_main=resume_data["is_main"],
            )
            resume.save()

            # Update created_at
            Resume.objects.filter(pk=resume.pk).update(created_at=created_at)
            resume.refresh_from_db()

            # Add random skills
            resume_skills = select_random_skills(skills, min_count=4, max_count=10)
            for skill in resume_skills:
                ResumeSkill.objects.create(
                    resume=resume,
                    skill=skill,
                    minimum_years=random.randint(0, 5),
                    proficiency_level=random.choice(proficiency_levels),
                )

            # Add random experiences
            num_experiences = random.randint(0, 4)
            for j in range(num_experiences):
                exp_data = generate_experience_data(lang)
                ResumeExperience.objects.create(
                    resume=resume,
                    **exp_data,
                )

            resumes.append(resume)

        # Generate embeddings if not skipped
        if not skip_embeddings and resumes:
            self._generate_resume_embeddings(resumes)

        return resumes

    def _create_company_applications(
            self,
            candidates: List[Candidate],
            vacancies: List[Vacancy],
            start_date: datetime,
            end_date: datetime,
    ) -> List[JobApplication]:
        """Create job applications for the company's vacancies."""
        import random
        from utils.company_data_generator import (
            generate_random_timestamp,
            generate_application_status,
        )

        applications = []

        if not vacancies:
            return applications

        # Get candidates with resumes
        candidates_with_resumes = []
        for candidate in candidates:
            resume = Resume.objects.filter(candidate=candidate).first()
            if resume:
                candidates_with_resumes.append((candidate, resume))

        if not candidates_with_resumes:
            return applications

        # Simulate realistic application patterns
        for candidate, resume in candidates_with_resumes:
            # Random chance of applying (70%)
            if random.random() > 0.7:
                continue

            # Each candidate applies to 1-4 vacancies
            num_applications = random.randint(1, min(4, len(vacancies)))
            candidate_vacancies = random.sample(vacancies, num_applications)

            for vacancy in candidate_vacancies:
                # Application date must be after vacancy creation and within range
                app_start = max(start_date, vacancy.created_at)
                if app_start >= end_date:
                    continue

                applied_at = generate_random_timestamp(app_start, end_date)

                # Generate realistic status distribution
                target_status, in_review_at, hired_at = generate_application_status(applied_at)

                try:
                    # Create application with APPLIED status first
                    application = JobApplication(
                        candidate=candidate,
                        vacancy=vacancy,
                        resume_used=resume,
                        cover_letter=f"Cover letter for {vacancy.title}",
                        status=ApplicationStatus.APPLIED,
                        is_active=True,
                        in_review_at=in_review_at,
                        hired_at=hired_at,
                    )
                    application.save()

                    # Update applied_at
                    JobApplication.objects.filter(pk=application.pk).update(
                        applied_at=applied_at
                    )
                    application.refresh_from_db()

                    # Now transition to the target status if different from APPLIED
                    if target_status != "APPLIED":
                        application.status = target_status
                        application.save()

                    applications.append(application)

                except Exception as e:
                    # Skip duplicates or other errors
                    logger.debug(f"Skipped application: {e}")
                    continue

        return applications

    def _create_company_vacancy_views(
            self,
            candidates: List[Candidate],
            vacancies: List[Vacancy],
            start_date: datetime,
            end_date: datetime,
    ) -> List[VacancyView]:
        """Create vacancy views for the company's vacancies."""
        import random
        from utils.company_data_generator import (
            generate_random_timestamp,
            generate_view_duration,
        )

        views = []

        for vacancy in vacancies:
            # Random number of candidates view each vacancy (5-30%)
            num_viewers = random.randint(
                max(1, len(candidates) // 20),
                max(2, len(candidates) // 4)
            )
            viewing_candidates = random.sample(
                candidates,
                min(num_viewers, len(candidates))
            )

            for candidate in viewing_candidates:
                # View happens after vacancy creation but within date range
                view_start = max(vacancy.created_at, start_date)
                view_end = end_date

                if view_start >= view_end:
                    continue

                viewed_at = generate_random_timestamp(view_start, view_end)
                duration = generate_view_duration()

                view = VacancyView(
                    vacancy=vacancy,
                    candidate=candidate,
                    session_start=viewed_at,
                    session_end=viewed_at + timedelta(seconds=duration),
                    duration_seconds=duration,
                )
                view.save()

                # Update viewed_at
                VacancyView.objects.filter(pk=view.pk).update(viewed_at=viewed_at)

                views.append(view)

        return views

    def _generate_vacancy_embeddings(self, vacancies: List[Vacancy]):
        """Generate embeddings for vacancies using the embedding service."""
        self.stdout.write("    Generating vacancy embeddings...")

        try:
            from apps.matching.services.embedding_tasks import generate_vacancy_embedding_task

            success_count = 0
            fail_count = 0

            for vacancy in vacancies:
                try:
                    result = generate_vacancy_embedding_task(vacancy.id)
                    if result:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Failed to generate embedding for vacancy {vacancy.id}: {e}")

            self.stdout.write(f"    Embeddings generated: {success_count} success, {fail_count} failed")

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Embedding generation skipped: {e}"))

    def _generate_resume_embeddings(self, resumes: List[Resume]):
        """Generate embeddings for resumes using the embedding service."""
        self.stdout.write("    Generating resume embeddings...")

        try:
            from apps.matching.services.embedding_tasks import generate_resume_embedding_task

            success_count = 0
            fail_count = 0

            for resume in resumes:
                try:
                    result = generate_resume_embedding_task(resume.id)
                    if result:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Failed to generate embedding for resume {resume.id}: {e}")

            self.stdout.write(f"    Embeddings generated: {success_count} success, {fail_count} failed")

        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Embedding generation skipped: {e}"))

    def _show_company_specific_summary(
            self,
            company: Company,
            candidates: List,
            vacancies: List,
            resumes: List,
            applications: List,
            views: List,
            start_date: datetime,
            end_date: datetime,
    ):
        """Show summary of company-specific data generation."""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS(f"COMPANY DATA GENERATION COMPLETE: {company.name}"))
        self.stdout.write("=" * 70)

        self.stdout.write(f"\nCompany: {company.name} (ID: {company.id})")
        self.stdout.write(f"Date Range: {start_date.date()} to {end_date.date()}")

        self.stdout.write("\nData Summary:")
        self.stdout.write(f"  Candidates:     {len(candidates)}")
        self.stdout.write(f"  Vacancies:      {len(vacancies)}")
        self.stdout.write(f"  Resumes:        {len(resumes)}")
        self.stdout.write(f"  Applications:   {len(applications)}")
        self.stdout.write(f"  Vacancy Views:  {len(views)}")

        # Show active/inactive vacancy count
        if vacancies:
            active_count = sum(1 for v in vacancies if v.is_active)
            inactive_count = len(vacancies) - active_count
            self.stdout.write("\nVacancy Status:")
            self.stdout.write(f"  - Active: {active_count}")
            self.stdout.write(f"  - Inactive (>30 days old): {inactive_count}")

        # Show application status distribution
        if applications:
            self.stdout.write("\nApplication Status Distribution:")
            status_counts = {}
            for app in applications:
                status_counts[app.status] = status_counts.get(app.status, 0) + 1
            for status, count in sorted(status_counts.items()):
                self.stdout.write(f"    {status}: {count}")

        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("Done! Company-specific data generation completed successfully."))

    def _delete_company_data(self, company: Company):
        """
        Delete all data related to a company.
        
        This deletes:
        - VacancyViews for the company's vacancies
        - JobApplications for the company's vacancies
        - VacancySkills for the company's vacancies
        - Vacancies created by the company's recruiters
        - RecruiterProfiles for the company's recruiters
        - Recruiters of the company
        - CompanyProfile of the company
        - The Company itself
        
        Note: Candidates and their resumes are NOT deleted as they may have
        applied to other companies as well.
        """
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.WARNING(f"DELETING ALL DATA FOR COMPANY: {company.name}"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"Company ID: {company.id}")
        self.stdout.write(self.style.WARNING("\nThis action will permanently delete all related data!"))
        
        # Confirm deletion (in production, you might want to add a confirmation prompt)
        self.stdout.write("\nStarting deletion process...\n")
        
        # Track deletion counts
        deletion_counts = {
            'vacancy_views': 0,
            'job_applications': 0,
            'vacancy_skills': 0,
            'vacancies': 0,
            'recruiter_profiles': 0,
            'recruiters': 0,
            'company_profiles': 0,
            'companies': 0,
        }
        
        try:
            with transaction.atomic():
                # 1. Delete VacancyViews for company's vacancies
                self.stdout.write("  1. Deleting vacancy views...")
                vacancy_ids = Vacancy.objects.filter(company=company).values_list('id', flat=True)
                views_deleted = VacancyView.objects.filter(vacancy_id__in=vacancy_ids).delete()
                deletion_counts['vacancy_views'] = views_deleted[0] if views_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['vacancy_views']} vacancy views")
                
                # 2. Delete JobApplications for company's vacancies
                self.stdout.write("  2. Deleting job applications...")
                applications_deleted = JobApplication.objects.filter(vacancy_id__in=vacancy_ids).delete()
                deletion_counts['job_applications'] = applications_deleted[0] if applications_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['job_applications']} job applications")
                
                # 3. Delete VacancySkills for company's vacancies
                self.stdout.write("  3. Deleting vacancy skills...")
                skills_deleted = VacancySkill.objects.filter(vacancy_id__in=vacancy_ids).delete()
                deletion_counts['vacancy_skills'] = skills_deleted[0] if skills_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['vacancy_skills']} vacancy skills")
                
                # 4. Delete Vacancies
                self.stdout.write("  4. Deleting vacancies...")
                vacancies_deleted = Vacancy.objects.filter(company=company).delete()
                deletion_counts['vacancies'] = vacancies_deleted[0] if vacancies_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['vacancies']} vacancies")
                
                # 5. Delete RecruiterProfiles for company's recruiters
                self.stdout.write("  5. Deleting recruiter profiles...")
                recruiter_ids = Recruiter.objects.filter(company=company).values_list('id', flat=True)
                recruiter_profiles_deleted = RecruiterProfile.objects.filter(recruiter_id__in=recruiter_ids).delete()
                deletion_counts['recruiter_profiles'] = recruiter_profiles_deleted[0] if recruiter_profiles_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['recruiter_profiles']} recruiter profiles")
                
                # 6. Delete Recruiters
                self.stdout.write("  6. Deleting recruiters...")
                recruiters_deleted = Recruiter.objects.filter(company=company).delete()
                deletion_counts['recruiters'] = recruiters_deleted[0] if recruiters_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['recruiters']} recruiters")
                
                # 7. Delete CompanyProfile
                self.stdout.write("  7. Deleting company profile...")
                company_profile_deleted = CompanyProfile.objects.filter(company=company).delete()
                deletion_counts['company_profiles'] = company_profile_deleted[0] if company_profile_deleted[0] else 0
                self.stdout.write(f"     Deleted {deletion_counts['company_profiles']} company profile(s)")
                
                # 8. Delete Company
                self.stdout.write("  8. Deleting company...")
                company_name = company.name
                company_id = company.id
                company.delete()
                deletion_counts['companies'] = 1
                self.stdout.write(f"     Deleted company: {company_name} (ID: {company_id})")
                
            # Show summary
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write(self.style.SUCCESS("DELETION COMPLETE"))
            self.stdout.write("=" * 70)
            self.stdout.write("\nDeletion Summary:")
            self.stdout.write(f"  Vacancy Views:       {deletion_counts['vacancy_views']}")
            self.stdout.write(f"  Job Applications:    {deletion_counts['job_applications']}")
            self.stdout.write(f"  Vacancy Skills:      {deletion_counts['vacancy_skills']}")
            self.stdout.write(f"  Vacancies:           {deletion_counts['vacancies']}")
            self.stdout.write(f"  Recruiter Profiles:  {deletion_counts['recruiter_profiles']}")
            self.stdout.write(f"  Recruiters:          {deletion_counts['recruiters']}")
            self.stdout.write(f"  Company Profiles:    {deletion_counts['company_profiles']}")
            self.stdout.write(f"  Companies:           {deletion_counts['companies']}")
            self.stdout.write("=" * 70)
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully deleted all data for company: {company_name}"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nError during deletion: {e}"))
            logger.exception(f"Error deleting company data for {company.name}: {e}")
            raise

    def _handle_data_generation(self, options):
        """Handle test data generation."""
        hr_only = options.get("hr_only", False)
        edupartner_only = options.get("edupartner_only", False)
        clear_existing = options.get("clear_existing", False)
        dry_run = options.get("dry_run", False)

        if dry_run:
            self._show_dry_run_summary(options)
            return

        # Clear existing data if requested
        if clear_existing:
            self._clear_all_data()

        # Create shared base data first
        self.stdout.write("\n" + "-" * 50)
        self.stdout.write("Creating Shared Base Data")
        self.stdout.write("-" * 50)

        with transaction.atomic():
            domains = self._create_domains()
            self._create_skills()

            # Create real universities (shared across both systems)
            self._create_real_universities(domains)

            # Create real companies (shared across both systems)
            self._create_real_companies(domains)

        # Run EduPartner data generation
        if not hr_only:
            self.stdout.write("\n" + "-" * 50)
            self.stdout.write("Generating EduPartner Analytics Data")
            self.stdout.write("-" * 50)

            # Create additional universities for EduPartner (imaginary ones)
            if options["universities"] > len(REAL_UNIVERSITIES):
                self._create_imaginary_universities(domains, options["universities"] - len(REAL_UNIVERSITIES))

            # Create additional companies for EduPartner
            if options.get("companies", 0) > len(REAL_COMPANIES):
                num_additional = options["companies"] - len(REAL_COMPANIES)
                self._create_imaginary_companies(domains, num_additional)

            # Create EduPartner specific data (students, applications, etc.)
            self._generate_edupartner_data(options)

        # Run HR Analytics data generation
        if not edupartner_only:
            self.stdout.write("\n" + "-" * 50)
            self.stdout.write("Generating HR Analytics Data")
            self.stdout.write("-" * 50)

            self._generate_hr_data(options)

        self._show_final_summary()

    def _clear_all_data(self):
        """Clear all existing test data."""
        self.stdout.write(self.style.WARNING("Clearing ALL existing test data..."))

        # Delete in order to avoid foreign key constraints
        VacancyView.objects.all().delete()
        self.stdout.write("  - Deleted vacancy views")

        JobApplication.objects.all().delete()
        self.stdout.write("  - Deleted applications")

        ResumeSkill.objects.all().delete()
        Resume.objects.all().delete()
        self.stdout.write("  - Deleted resumes")

        VacancySkill.objects.all().delete()
        Vacancy.objects.all().delete()
        self.stdout.write("  - Deleted vacancies")

        CandidateProfile.objects.all().delete()
        Candidate.objects.all().delete()
        self.stdout.write("  - Deleted candidates")

        RecruiterProfile.objects.all().delete()
        Recruiter.objects.all().delete()
        self.stdout.write("  - Deleted recruiters")

        CompanyProfile.objects.all().delete()
        Company.objects.all().delete()
        self.stdout.write("  - Deleted companies")

        Faculty.objects.all().delete()
        EduPartner.objects.all().delete()
        self.stdout.write("  - Deleted universities/edupartners")

        self.stdout.write(self.style.SUCCESS("All existing data cleared"))

    def _create_domains(self) -> Dict[str, Domain]:
        """Create domains from shared configuration."""
        domains = {}
        for name in DOMAIN_NAMES:
            domain, created = Domain.objects.get_or_create(
                name=name,
                defaults={"description": f"Domain for {name} related professions"},
            )
            domains[name] = domain
            if created:
                self.stdout.write(f"  Created domain: {name}")

        self.stdout.write(f"  Total domains: {len(domains)}")
        return domains

    def _create_skills(self) -> Dict[str, Skill]:
        """Create skills from shared configuration."""
        skills = {}
        for name in SKILL_NAMES:
            skill, created = Skill.objects.get_or_create(
                name=name,
                defaults={"description": f"Professional skill in {name}"},
            )
            skills[name] = skill

        self.stdout.write(f"  Created/verified {len(skills)} skills")
        return skills

    def _create_real_universities(self, domains: Dict[str, Domain]) -> List[EduPartner]:
        """Create real universities from shared configuration."""
        universities = []

        for uni_data in REAL_UNIVERSITIES:
            # Get or create university type
            uni_type, _ = EduPartnersType.objects.get_or_create(
                name=uni_data["type"],
                defaults={"name": uni_data["type"]},
            )

            # Check if university already exists
            existing = EduPartner.objects.filter(name=uni_data["name"]).first()
            if existing:
                universities.append(existing)
                self.stdout.write(f"  University already exists: {existing.name}")
                continue

            # Create university
            university = EduPartner.objects.create(
                name=uni_data["name"],
                edupartner_type=uni_type,
                country=uni_data["country"],
                city=uni_data["city"],
                website=uni_data["website"],
                description=uni_data["description"],
                is_active=True,
            )

            # Create faculties
            for fac_data in uni_data["faculties"]:
                domain = domains.get(fac_data["domain"])
                Faculty.objects.create(
                    name=fac_data["name"],
                    edupartner=university,
                    domain=domain,
                    is_active=True,
                )

            universities.append(university)
            self.stdout.write(f"  Created university: {university.name} with {len(uni_data['faculties'])} faculties")

        return universities

    def _create_imaginary_universities(self, domains: Dict[str, Domain], count: int) -> List[EduPartner]:
        """Create imaginary universities for EduPartner analytics."""
        universities = []
        available = IMAGINARY_UNIVERSITIES[:count]

        for uni_data in available:
            # Get or create university type
            uni_type, _ = EduPartnersType.objects.get_or_create(
                name=uni_data["type"],
                defaults={"name": uni_data["type"]},
            )

            # Check if university already exists
            existing = EduPartner.objects.filter(name=uni_data["name"]).first()
            if existing:
                universities.append(existing)
                continue

            # Create university
            university = EduPartner.objects.create(
                name=uni_data["name"],
                edupartner_type=uni_type,
                country=uni_data["country"],
                city=uni_data["city"],
                website=uni_data["website"],
                description=uni_data["description"],
                is_active=True,
            )

            # Create faculties
            for fac_data in uni_data["faculties"]:
                domain = domains.get(fac_data["domain"])
                Faculty.objects.create(
                    name=fac_data["name"],
                    edupartner=university,
                    domain=domain,
                    is_active=True,
                )

            universities.append(university)
            self.stdout.write(f"  Created imaginary university: {university.name}")

        return universities

    def _create_real_companies(self, domains: Dict[str, Domain]) -> List[Company]:
        """Create real companies from shared configuration."""
        import random

        companies = []

        for company_data in REAL_COMPANIES:
            domain = domains.get(company_data["domain"])

            # Check if company already exists
            existing = Company.objects.filter(name=company_data["name"]).first()
            if existing:
                companies.append(existing)
                self.stdout.write(f"  Company already exists: {existing.name}")
                continue

            # Create company
            company = Company.objects.create(
                name=company_data["name"],
                domain=domain,
                tin=company_data["tin"],
                is_active=True,
            )

            # Create company profile
            CompanyProfile.objects.create(
                company=company,
                description=company_data["description"],
                address=company_data["address"],
                website=company_data["website"],
            )

            # Create recruiter
            recruiter = Recruiter.objects.create(
                email=f"hr@{company_data['name'].lower()}.uz",
                company=company,
                is_recruiter=True,
                is_active=True,
            )

            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"{company_data['name']} HR Manager",
                phone=f"+99890{random.randint(1000000, 9999999)}",
            )

            companies.append(company)
            self.stdout.write(f"  Created real company: {company.name}")

        return companies

    def _create_imaginary_companies(self, domains: Dict[str, Domain], count: int) -> List[Company]:
        """Create imaginary companies for analytics."""
        import random

        companies = []
        available = IMAGINARY_COMPANIES[:count]

        for company_data in available:
            domain = domains.get(company_data["domain"])

            # Check if company already exists
            existing = Company.objects.filter(name=company_data["name"]).first()
            if existing:
                companies.append(existing)
                continue

            # Create company
            tin = f"30{random.randint(1000000, 9999999)}"
            company = Company.objects.create(
                name=company_data["name"],
                domain=domain,
                tin=tin,
                is_active=True,
            )

            # Create company profile
            CompanyProfile.objects.create(
                company=company,
                description=f"{company_data['name']} is a leading company in {company_data['domain']}.",
                address=f"{random.randint(1, 100)} Main Street, Tashkent",
                website=f"https://{company_data['name'].lower().replace(' ', '')}.uz",
            )

            # Create recruiter
            recruiter = Recruiter.objects.create(
                email=f"hr@{company_data['name'].lower().replace(' ', '')}.uz",
                company=company,
                is_recruiter=True,
                is_active=True,
            )

            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"{company_data['name']} HR Manager",
                phone=f"+99890{random.randint(1000000, 9999999)}",
            )

            companies.append(company)
            self.stdout.write(f"  Created imaginary company: {company.name}")

        return companies

    def _generate_edupartner_data(self, options):
        """Generate EduPartner specific test data (students, applications, etc.)."""
        # Note: This uses the existing create_edupartner_test_data command internally
        # but with --no-clear flag to preserve shared data

        # The EduPartner command will generate:
        # - Students for each university
        # - Resumes for students
        # - Vacancies over time
        # - Applications from students

        self.stdout.write("  Generating EduPartner specific data...")
        self.stdout.write("  (Using existing universities and companies as base)")

        # We can call the sub-command or implement logic here
        # For now, let's implement the key parts directly to maintain control

        from apps.edupartners.management.commands.create_edupartner_test_data import Command as EduPartnerCommand

        edu_cmd = EduPartnerCommand()
        edu_cmd.stdout = self.stdout
        edu_cmd.style = self.style

        # Update date ranges
        edu_cmd.DATA_START_DATE = get_data_start_date()
        edu_cmd.DATA_END_DATE = get_data_end_date()
        edu_cmd.APPLICATION_START_DATE = get_data_start_date()
        edu_cmd.APPLICATION_END_DATE = get_data_end_date()

        # Get existing data
        universities = list(EduPartner.objects.filter(is_active=True))
        domains = {d.name: d for d in Domain.objects.all()}
        skills = {s.name: s for s in Skill.objects.all()}
        companies = list(Company.objects.filter(is_active=True))

        if not universities:
            self.stdout.write(self.style.WARNING("No universities found. Skipping EduPartner data generation."))
            return

        with transaction.atomic():
            # Create students
            students = edu_cmd.create_students(
                universities,
                options.get("students_per_university", DefaultConfig.EDUPARTNER_STUDENTS_PER_UNIVERSITY)
            )

            # Create vacancies spread across months
            vacancies = edu_cmd.create_vacancies_by_month(
                companies,
                DefaultConfig.EDUPARTNER_VACANCIES_PER_MONTH,
                domains,
                skills,
            )

            # Create resumes for students
            edu_cmd.create_resumes(students, skills)

            # Create applications
            edu_cmd.create_applications(
                students,
                vacancies,
                DefaultConfig.EDUPARTNER_APPLICATIONS_PER_VACANCY_MIN,
                DefaultConfig.EDUPARTNER_APPLICATIONS_PER_VACANCY_MAX,
            )

    def _generate_hr_data(self, options):
        """Generate HR Analytics specific test data."""
        self.stdout.write("  Generating HR Analytics specific data...")
        self.stdout.write("  (Using existing universities and companies as base)")

        from apps.general.management.commands.generate_hr_analytics_test_data import Command as HRCommand

        hr_cmd = HRCommand()
        hr_cmd.stdout = self.stdout
        hr_cmd.style = self.style

        # Update date ranges
        hr_cmd.DATA_START_DATE = get_data_start_date()
        hr_cmd.DATA_END_DATE = get_data_end_date()
        hr_cmd.APPLICATION_START_DATE = get_data_start_date()
        hr_cmd.APPLICATION_END_DATE = get_data_end_date()
        hr_cmd.INACTIVE_VACANCY_DATE = get_data_end_date() - timedelta(days=30)

        # Get existing data
        university = EduPartner.objects.filter(is_active=True).first()
        domains = list(Domain.objects.all())
        skills = list(Skill.objects.all())
        companies = list(Company.objects.filter(is_active=True))

        if not university:
            self.stdout.write(self.style.WARNING("No university found. Skipping HR data generation."))
            return

        skip_embeddings = options.get("skip_embeddings", False)

        with transaction.atomic():
            # Create candidates
            candidates = hr_cmd._create_candidates(
                options.get("candidates", DefaultConfig.HR_CANDIDATES),
                university,
            )

            # Create vacancies (using existing companies)
            vacancies = hr_cmd._create_vacancies(
                companies,
                DefaultConfig.HR_VACANCIES_PER_COMPANY,
                domains,
                skills,
                skip_embeddings,
            )

            # Create resumes
            hr_cmd._create_resumes(
                candidates,
                skills,
                domains,
                skip_embeddings,
            )

            # Create applications
            hr_cmd._create_applications(candidates, vacancies)

            # Create vacancy views
            hr_cmd._create_vacancy_views(candidates, vacancies)

    def _show_dry_run_summary(self, options):
        """Show what would be created in dry run mode."""
        self.stdout.write(self.style.WARNING("\nDRY RUN MODE - No data will be created"))
        self.stdout.write("\nShared Base Data:")
        self.stdout.write(f"  - Domains: {len(DOMAIN_NAMES)}")
        self.stdout.write(f"  - Skills: {len(SKILL_NAMES)}")
        self.stdout.write(f"  - Real Universities: {len(REAL_UNIVERSITIES)}")
        self.stdout.write(f"  - Real Companies: {len(REAL_COMPANIES)}")

        if not options.get("hr_only"):
            self.stdout.write("\nEduPartner Analytics Data:")
            total_universities = options.get("universities", DefaultConfig.EDUPARTNER_UNIVERSITIES)
            students = total_universities * options.get("students_per_university", DefaultConfig.EDUPARTNER_STUDENTS_PER_UNIVERSITY)
            self.stdout.write(f"  - Universities: {total_universities}")
            self.stdout.write(f"  - Students: ~{students}")
            self.stdout.write(f"  - Additional Companies: ~{options.get('companies', 30) - len(REAL_COMPANIES)}")

        if not options.get("edupartner_only"):
            self.stdout.write("\nHR Analytics Data:")
            self.stdout.write(f"  - Candidates: {options.get('candidates', DefaultConfig.HR_CANDIDATES)}")
            self.stdout.write(f"  - Vacancies per company: {DefaultConfig.HR_VACANCIES_PER_COMPANY}")

    def _show_final_summary(self):
        """Show final summary of all created data."""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("UNIFIED DATA GENERATION COMPLETE"))
        self.stdout.write("=" * 70)

        # Count entities
        self.stdout.write("\nData Summary:")
        self.stdout.write(f"  Universities:   {EduPartner.objects.count()}")
        self.stdout.write(f"  Faculties:      {Faculty.objects.count()}")
        self.stdout.write(f"  Companies:      {Company.objects.count()}")
        self.stdout.write(f"  Candidates:     {Candidate.objects.count()}")
        self.stdout.write(f"  Recruiters:     {Recruiter.objects.count()}")
        self.stdout.write(f"  Vacancies:      {Vacancy.objects.count()}")
        self.stdout.write(f"  Resumes:        {Resume.objects.count()}")
        self.stdout.write(f"  Applications:   {JobApplication.objects.count()}")

        # Application status distribution
        self.stdout.write("\nApplication Status Distribution:")
        for status in ApplicationStatus:
            count = JobApplication.objects.filter(status=status).count()
            if count > 0:
                self.stdout.write(f"    {status.label}: {count}")

        self.stdout.write("=" * 70)
