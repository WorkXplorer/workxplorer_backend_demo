"""
Management command to generate test data for HR Analytics.

This command creates realistic test data with varied timestamps across different
days to properly test HR Analytics functionality. It creates:
- Real companies (Safia, Alif) plus imaginary ones
- Real university (UTAS - University of Tashkent for Applied Sciences)
- Candidates with profiles
- Vacancies in 3 languages (Uzbek, Russian, English) with embeddings
- Resumes in 3 languages with embeddings
- Job applications with various statuses
- Vacancy views

Data generation follows realistic patterns:
- Vacancies created from 2026 to current date
- Vacancies older than 1 month are marked inactive
- Applications from 2026 to current date
- Resumes created from 2026 to current date

Note: When running this command standalone, it will NOT delete existing data
by default. Use --clear-existing to clear data first.
"""

import random
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.authentication.models import Candidate, Company, Recruiter
from apps.profiles.models import CandidateProfile, RecruiterProfile, CompanyProfile
from apps.domain.models import Domain
from apps.skills.models import Skill
from apps.vacancies.models import Vacancy, VacancySkill, VacancyView
from apps.resumes.models import Resume, ResumeSkill, ResumeExperience
from apps.resumes.models.choices import ProficiencyLevel, WorkStatus
from apps.applications.models import JobApplication
from apps.applications.models.choices import ApplicationStatus
from apps.edupartners.models import EduPartner, EduPartnersType, Faculty

# Import shared configuration
from utils.shared_test_data_config import (
    DOMAIN_NAMES as SHARED_DOMAIN_NAMES,
    SKILL_NAMES as SHARED_SKILL_NAMES,
    REAL_COMPANIES as SHARED_REAL_COMPANIES,
    IMAGINARY_COMPANIES as SHARED_IMAGINARY_COMPANIES,
    REAL_UNIVERSITIES as SHARED_REAL_UNIVERSITIES,
    JOB_TITLES_MULTILINGUAL as SHARED_JOB_TITLES,
    VACANCY_DESCRIPTIONS as SHARED_VACANCY_DESCRIPTIONS,
    RESUME_DESCRIPTIONS as SHARED_RESUME_DESCRIPTIONS,
    FIRST_NAMES_MALE,
    FIRST_NAMES_FEMALE,
    LAST_NAMES,
    CITIES,
    DefaultConfig,
    get_data_start_date,
    get_data_end_date,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate test data for HR Analytics with varied timestamps and multilingual content"

    # Date range constants (2026 to current date) - will be updated from shared config
    DATA_START_DATE = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    DATA_END_DATE = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    # Application date range (same as data range)
    APPLICATION_START_DATE = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    APPLICATION_END_DATE = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    # One month before end date (vacancies older than this are inactive)
    INACTIVE_VACANCY_DATE = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999) - timedelta(days=30)

    # Domain names - use shared config
    DOMAIN_NAMES = SHARED_DOMAIN_NAMES

    # Skills for vacancies/resumes - use shared config
    SKILL_NAMES = SHARED_SKILL_NAMES

    # Real and imaginary company data - use shared config
    REAL_COMPANIES = SHARED_REAL_COMPANIES

    IMAGINARY_COMPANIES = SHARED_IMAGINARY_COMPANIES

    # University data - use shared config (first university from the list)
    UNIVERSITY_DATA = SHARED_REAL_UNIVERSITIES[0] if SHARED_REAL_UNIVERSITIES else {
        "name": "UTAS (University of Tashkent for Applied Sciences)",
        "short_name": "UTAS",
        "type": "University",
        "country": "Uzbekistan",
        "city": "Tashkent",
        "website": "https://utas.uz",
        "description": "Amaliy fanlar bo'yicha Toshkent universiteti.",
        "faculties": [
            {"name": "Computer Science", "domain": "Information Technology"},
            {"name": "Business Administration", "domain": "Business & Management"},
        ],
    }

    # Names - use shared config
    FIRST_NAMES = FIRST_NAMES_MALE + FIRST_NAMES_FEMALE
    LAST_NAMES = LAST_NAMES
    CITIES = CITIES

    # Job titles in 3 languages - use shared config
    JOB_TITLES_MULTILINGUAL = SHARED_JOB_TITLES

    # Vacancy descriptions - use shared config
    VACANCY_DESCRIPTIONS = SHARED_VACANCY_DESCRIPTIONS

    # Resume descriptions - use shared config
    RESUME_DESCRIPTIONS = SHARED_RESUME_DESCRIPTIONS

    def add_arguments(self, parser):
        parser.add_argument(
            "--companies",
            type=int,
            default=DefaultConfig.HR_COMPANIES,
            help=f"Number of companies to create (default: {DefaultConfig.HR_COMPANIES}, includes real companies)",
        )
        parser.add_argument(
            "--candidates",
            type=int,
            default=DefaultConfig.HR_CANDIDATES,
            help=f"Number of candidates to create (default: {DefaultConfig.HR_CANDIDATES})",
        )
        parser.add_argument(
            "--vacancies-per-company",
            type=int,
            default=DefaultConfig.HR_VACANCIES_PER_COMPANY,
            help=f"Number of vacancies per company (default: {DefaultConfig.HR_VACANCIES_PER_COMPANY})",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing test data before creating new data (NOT enabled by default)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating data",
        )
        parser.add_argument(
            "--skip-embeddings",
            action="store_true",
            help="Skip embedding generation (faster for testing)",
        )
        parser.add_argument(
            "--use-existing-base",
            action="store_true",
            help="Use existing universities and companies instead of creating new ones",
        )

    def handle(self, *args, **options):
        # Update date ranges from shared config
        self.DATA_START_DATE = get_data_start_date()
        self.DATA_END_DATE = get_data_end_date()
        self.APPLICATION_START_DATE = get_data_start_date()
        self.APPLICATION_END_DATE = get_data_end_date()
        self.INACTIVE_VACANCY_DATE = get_data_end_date() - timedelta(days=30)

        self.stdout.write(
            self.style.SUCCESS("Starting HR Analytics test data generation...")
        )
        self.stdout.write(f"  - Companies: {options['companies']}")
        self.stdout.write(f"  - Candidates: {options['candidates']}")
        self.stdout.write(f"  - Vacancies per company: {options['vacancies_per_company']}")
        self.stdout.write(f"  - Data range: {self.DATA_START_DATE.date()} to {self.DATA_END_DATE.date()}")
        self.stdout.write(
            f"  - Applications range: {self.APPLICATION_START_DATE.date()} to {self.APPLICATION_END_DATE.date()}"
        )

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN MODE - No data will be created")
            )
            self._show_dry_run_summary(options)
            return

        # Only clear existing data if explicitly requested
        if options.get("clear_existing"):
            self._clear_existing_data()

        with transaction.atomic():
            # Create base data
            domains = self._create_domains()
            skills = self._create_skills()

            # Create university
            university = self._create_university(domains)

            # Create companies
            companies = self._create_companies(
                options["companies"],
                domains,
            )

            # Create candidates
            candidates = self._create_candidates(
                options["candidates"],
                university,
            )

            # Create vacancies with multilingual content
            vacancies = self._create_vacancies(
                companies,
                options["vacancies_per_company"],
                domains,
                skills,
                options.get("skip_embeddings", False),
            )

            # Create resumes with multilingual content
            resumes = self._create_resumes(
                candidates,
                skills,
                domains,
                options.get("skip_embeddings", False),
            )

            # Create applications (Dec 20, 2025 - Jan 8, 2026)
            applications = self._create_applications(candidates, vacancies)

            # Create vacancy views
            views = self._create_vacancy_views(candidates, vacancies)

        self._show_summary(companies, candidates, vacancies, applications, views, resumes)

    def _show_dry_run_summary(self, options):
        """Show what would be created in dry run mode."""
        total_vacancies = options["companies"] * options["vacancies_per_company"]
        estimated_applications = int(options["candidates"] * 0.7 * 2)
        estimated_views = int(options["candidates"] * total_vacancies * 0.2)

        self.stdout.write("\nEstimated data to be created:")
        self.stdout.write(f"  - Domains: {len(self.DOMAIN_NAMES)}")
        self.stdout.write(f"  - Skills: {len(self.SKILL_NAMES)}")
        self.stdout.write("  - University: 1 (UTAS)")
        self.stdout.write(f"  - Companies: {options['companies']} (2 real + {options['companies'] - 2} imaginary)")
        self.stdout.write(f"  - Recruiters: {options['companies']}")
        self.stdout.write(f"  - Candidates: {options['candidates']}")
        self.stdout.write(f"  - Vacancies: {total_vacancies} (multilingual: uz/ru/en)")
        self.stdout.write(f"  - Resumes: ~{int(options['candidates'] * 0.85)} (multilingual: uz/ru/en)")
        self.stdout.write(f"  - Applications (approx): {estimated_applications}")
        self.stdout.write(f"  - Vacancy views (approx): {estimated_views}")

    def _clear_existing_data(self):
        """Clear all existing test data."""
        self.stdout.write(self.style.WARNING("Clearing ALL existing data..."))

        # Delete in order to avoid foreign key constraints
        VacancyView.objects.all().delete()
        self.stdout.write("  - Deleted vacancy views")

        JobApplication.objects.all().delete()
        self.stdout.write("  - Deleted applications")

        ResumeExperience.objects.all().delete()
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

        # Clear faculties but keep edu partner types
        Faculty.objects.all().delete()
        EduPartner.objects.all().delete()
        self.stdout.write("  - Deleted universities/edupartners")

        self.stdout.write(self.style.SUCCESS("All existing data cleared"))

    def _create_domains(self) -> List[Domain]:
        """Create domains if they don't exist."""
        domains = []
        for name in self.DOMAIN_NAMES:
            domain, created = Domain.objects.get_or_create(
                name=name,
                defaults={"description": f"Domain for {name} related professions"},
            )
            domains.append(domain)
            if created:
                self.stdout.write(f"  Created domain: {name}")
        self.stdout.write(f"  Ensured {len(domains)} domains exist")
        return domains

    def _create_skills(self) -> List[Skill]:
        """Create skills if they don't exist."""
        skills = []
        for name in self.SKILL_NAMES:
            skill, created = Skill.objects.get_or_create(
                name=name,
                defaults={"description": f"Skill in {name}"},
            )
            skills.append(skill)
        self.stdout.write(f"  Ensured {len(skills)} skills exist")
        return skills

    def _create_university(self, domains: List[Domain]) -> EduPartner:
        """Create UTAS university with faculties."""
        # Create or get university type
        uni_type, _ = EduPartnersType.objects.get_or_create(
            name="University",
            defaults={"name": "University"},
        )

        # Create UTAS
        uni_data = self.UNIVERSITY_DATA
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
        domain_map = {d.name: d for d in domains}
        for fac_data in uni_data["faculties"]:
            domain = domain_map.get(fac_data["domain"])
            Faculty.objects.create(
                name=fac_data["name"],
                edupartner=university,
                domain=domain,
                is_active=True,
            )

        self.stdout.write(f"  Created university: {university.name} with {len(uni_data['faculties'])} faculties")
        return university

    def _create_companies(
            self, count: int, domains: List[Domain]
    ) -> List[Company]:
        """Create companies with recruiters and profiles."""
        companies = []
        domain_map = {d.name: d for d in domains}

        # First, create real companies (Safia, Alif)
        for real_company in self.REAL_COMPANIES:
            domain = domain_map.get(real_company["domain"])
            company = Company.objects.create(
                name=real_company["name"],
                domain=domain,
                tin=real_company["tin"],
                is_active=True,
            )

            CompanyProfile.objects.create(
                company=company,
                description=real_company["description"],
                address=real_company["address"],
                website=real_company["website"],
            )

            # Create recruiter for each company
            recruiter = Recruiter.objects.create(
                email=f"hr@{real_company['name'].lower()}.uz",
                company=company,
                is_recruiter=True,
                is_active=True,
            )

            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"{real_company['name']} HR Manager",
                phone=f"+99890{random.randint(1000000, 9999999)}",
            )

            companies.append(company)
            self.stdout.write(f"  Created real company: {company.name}")

        # Create imaginary companies
        num_imaginary = count - len(self.REAL_COMPANIES)
        shuffled_imaginary = random.sample(
            self.IMAGINARY_COMPANIES,
            min(num_imaginary, len(self.IMAGINARY_COMPANIES))
        )

        for i, img_company in enumerate(shuffled_imaginary):
            domain = domain_map.get(img_company["domain"])
            tin = f"30{random.randint(1000000, 9999999)}"

            company = Company.objects.create(
                name=img_company["name"],
                domain=domain,
                tin=tin,
                is_active=True,
            )

            CompanyProfile.objects.create(
                company=company,
                description=f"{img_company['name']} is a leading company in {img_company['domain']}.",
                address=f"{random.randint(1, 100)} Main Street, {random.choice(self.CITIES)}",
                website=f"https://{img_company['name'].lower().replace(' ', '')}.uz",
            )

            recruiter = Recruiter.objects.create(
                email=f"hr@{img_company['name'].lower().replace(' ', '')}.uz",
                company=company,
                is_recruiter=True,
                is_active=True,
            )

            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"{img_company['name']} HR Manager",
                phone=f"+99890{random.randint(1000000, 9999999)}",
            )

            companies.append(company)

        self.stdout.write(
            f"  Created {len(companies)} companies ({len(self.REAL_COMPANIES)} real, {len(companies) - len(self.REAL_COMPANIES)} imaginary)"
        )
        return companies

    def _create_candidates(
            self, count: int, university: EduPartner
    ) -> List[Candidate]:
        """Create candidates with profiles."""
        candidates = []
        faculties = list(university.faculties.all())
        regions = list(CandidateProfile.RegionChoices)

        for i in range(count):
            first_name = random.choice(self.FIRST_NAMES)
            last_name = random.choice(self.LAST_NAMES)

            # Random birth date (18-35 years old from perspective of Jan 2026)
            birth_year = random.randint(1991, 2007)
            birth_month = random.randint(1, 12)
            birth_day = random.randint(1, 28)
            birth_date = datetime(birth_year, birth_month, birth_day).date()

            email = f"{first_name.lower()}.{last_name.lower()}.{i}@testmail.uz"

            # Randomly assign some candidates to UTAS
            assign_to_utas = random.random() < 0.4  # 40% chance

            candidate = Candidate.objects.create(
                email=email,
                date_of_birth=birth_date,
                is_candidate=True,
                is_active=True,
                edupartner=university if assign_to_utas else None,
                faculty=random.choice(faculties) if assign_to_utas and faculties else None,
            )

            CandidateProfile.objects.create(
                candidate=candidate,
                full_name=f"{first_name} {last_name}",
                candidate_email=email,
                region=random.choice(regions),
                phone=f"+99890{random.randint(1000000, 9999999)}",
            )

            candidates.append(candidate)

        self.stdout.write(f"  Created {len(candidates)} candidates with profiles")
        return candidates

    def _get_random_timestamp(self, start_date: datetime, end_date: datetime) -> datetime:
        """Generate a random timestamp within the specified range."""
        time_delta = end_date - start_date
        random_days = random.randint(0, time_delta.days)
        random_hours = random.randint(0, 23)
        random_minutes = random.randint(0, 59)
        return start_date + timedelta(
            days=random_days, hours=random_hours, minutes=random_minutes
        )

    def _get_random_language(self) -> str:
        """Get a random language code."""
        return random.choice(["uz", "ru", "en"])

    def _create_vacancies(
            self,
            companies: List[Company],
            vacancies_per_company: int,
            domains: List[Domain],
            skills: List[Skill],
            skip_embeddings: bool,
    ) -> List[Vacancy]:
        """Create vacancies with multilingual content and varied timestamps."""
        vacancies = []
        employment_types = ["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP"]
        employment_formats = ["ON_SITE", "REMOTE", "HYBRID"]

        for company in companies:
            recruiter = company.recruiters.first()
            if not recruiter:
                continue

            for i in range(vacancies_per_company):
                # Generate random timestamp between 2024 and Jan 8, 2026
                created_at = self._get_random_timestamp(
                    self.DATA_START_DATE,
                    self.DATA_END_DATE
                )

                # Determine if vacancy should be inactive (older than 1 month)
                is_active = created_at > self.INACTIVE_VACANCY_DATE

                # Pick random language for this vacancy
                lang = self._get_random_language()
                job_title_data = random.choice(self.JOB_TITLES_MULTILINGUAL)
                title = job_title_data[lang]

                about_us = random.choice(self.VACANCY_DESCRIPTIONS["about_us"][lang])
                requirements = random.choice(self.VACANCY_DESCRIPTIONS["requirements"][lang])
                responsibilities = random.choice(self.VACANCY_DESCRIPTIONS["responsibilities"][lang])

                vacancy = Vacancy(
                    created_by=recruiter,
                    title=title,
                    domain=random.choice(domains),
                    company=company,
                    experience=random.randint(0, 7),
                    contact_email=f"jobs@{company.name.lower().replace(' ', '')}.uz",
                    salary_min=Decimal(random.randint(300, 800)) * 100000,
                    salary_max=Decimal(random.randint(800, 2000)) * 100000,
                    salary_currency="UZS",
                    employment_type=random.choice(employment_types),
                    employment_format=random.choice(employment_formats),
                    about_us=about_us,
                    requirements=requirements,
                    responsibilities=responsibilities,
                    is_active=is_active,
                    number_of_positions=random.randint(1, 5),
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
                vacancy_skills = random.sample(skills, random.randint(3, 8))
                for skill in vacancy_skills:
                    VacancySkill.objects.create(
                        vacancy=vacancy,
                        skill=skill,
                        is_required=random.choice([True, False]),
                        minimum_years=random.randint(0, 3),
                        proficiency_level=random.choice([
                            "BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"
                        ]),
                    )

                vacancies.append(vacancy)

        self.stdout.write(f"  Created {len(vacancies)} vacancies with varied timestamps")

        # Generate embeddings if not skipped
        if not skip_embeddings:
            self._generate_vacancy_embeddings(vacancies)

        return vacancies

    def _generate_vacancy_embeddings(self, vacancies: List[Vacancy]):
        """Generate embeddings for vacancies using the embedding service."""
        self.stdout.write("  Generating vacancy embeddings...")

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

            self.stdout.write(f"  Embeddings generated: {success_count} success, {fail_count} failed")

        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"  Embedding generation skipped: {e}")
            )

    def _create_resumes(
            self,
            candidates: List[Candidate],
            skills: List[Skill],
            domains: List[Domain],
            skip_embeddings: bool,
    ) -> List[Resume]:
        """Create resumes with multilingual content."""
        resumes = []
        work_statuses = [
            WorkStatus.ACTIVELY_LOOKING,
            WorkStatus.OPEN_TO_OPPORTUNITIES,
            WorkStatus.NOT_LOOKING,
        ]
        proficiency_levels = list(ProficiencyLevel)

        for candidate in candidates:
            # 85% of candidates have resumes
            if random.random() > 0.85:
                continue

            try:
                profile = CandidateProfile.objects.get(candidate=candidate)
            except CandidateProfile.DoesNotExist:
                continue

            # Pick random language for this resume
            lang = self._get_random_language()
            job_title_data = random.choice(self.JOB_TITLES_MULTILINGUAL)
            position = job_title_data[lang]
            title = f"{profile.full_name} - {position}"

            years_exp = random.randint(0, 10)
            description_template = random.choice(self.RESUME_DESCRIPTIONS[lang])
            description = description_template.format(
                position=position,
                years=years_exp
            )

            # Random creation date (2024 - Jan 8, 2026)
            created_at = self._get_random_timestamp(
                self.DATA_START_DATE,
                self.DATA_END_DATE
            )

            resume = Resume(
                candidate=candidate,
                title=title,
                description=description,
                position=position,
                domain=random.choice(domains),
                work_status=random.choice(work_statuses),
                is_active=True,
                is_main=True,
            )
            resume.save()

            # Update created_at
            Resume.objects.filter(pk=resume.pk).update(created_at=created_at)
            resume.refresh_from_db()

            # Add random skills
            resume_skills = random.sample(skills, random.randint(4, 10))
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
                exp_start_year = random.randint(2018, 2024)
                exp_start_month = random.randint(1, 12)
                exp_end_year = random.randint(exp_start_year, 2025)
                exp_end_month = random.randint(1, 12)

                ResumeExperience.objects.create(
                    resume=resume,
                    company=random.choice(self.IMAGINARY_COMPANIES)["name"],
                    role=random.choice(self.JOB_TITLES_MULTILINGUAL)[lang],
                    country="Uzbekistan",
                    city=random.choice(self.CITIES),
                    start_date=datetime(exp_start_year, exp_start_month, 1).date(),
                    end_date=datetime(exp_end_year, exp_end_month, 1).date() if random.random() > 0.3 else None,
                    description="Worked as a professional in various projects.",
                )

            resumes.append(resume)

        self.stdout.write(f"  Created {len(resumes)} resumes with varied timestamps")

        # Generate embeddings if not skipped
        if not skip_embeddings:
            self._generate_resume_embeddings(resumes)

        return resumes

    def _generate_resume_embeddings(self, resumes: List[Resume]):
        """Generate embeddings for resumes using the embedding service."""
        self.stdout.write("  Generating resume embeddings...")

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

            self.stdout.write(f"  Embeddings generated: {success_count} success, {fail_count} failed")

        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"  Embedding generation skipped: {e}")
            )

    def _create_applications(
            self,
            candidates: List[Candidate],
            vacancies: List[Vacancy],
    ) -> List[JobApplication]:
        """Create job applications within the date range (Dec 20, 2025 - Jan 8, 2026)."""
        applications = []

        # Get only active vacancies that exist before application period
        eligible_vacancies = [
            v for v in vacancies
            if v.created_at < self.APPLICATION_END_DATE
        ]

        if not eligible_vacancies:
            self.stdout.write(self.style.WARNING("No eligible vacancies for applications"))
            return applications

        # Get candidates with resumes
        candidates_with_resumes = []
        for c in candidates:
            resume = Resume.objects.filter(candidate=c).first()
            if resume:
                candidates_with_resumes.append((c, resume))

        if not candidates_with_resumes:
            self.stdout.write(self.style.WARNING("No candidates with resumes found"))
            return applications

        # Simulate realistic application patterns
        for candidate, resume in candidates_with_resumes:
            # Random chance of applying (70%)
            if random.random() > 0.7:
                continue

            # Each candidate applies to 1-4 vacancies
            num_applications = random.randint(1, 4)
            candidate_vacancies = random.sample(
                eligible_vacancies,
                min(num_applications, len(eligible_vacancies))
            )

            for vacancy in candidate_vacancies:
                # Generate random application date within range
                applied_at = self._get_random_timestamp(
                    max(self.APPLICATION_START_DATE, vacancy.created_at),
                    self.APPLICATION_END_DATE
                )

                # Generate realistic status distribution
                target_status, in_review_at, hired_at = self._generate_application_status(applied_at)

                try:
                    # Create application with APPLIED status first
                    application = JobApplication(
                        candidate=candidate,
                        vacancy=vacancy,
                        resume_used=resume,
                        cover_letter=f"Cover letter for {vacancy.title}",
                        status=ApplicationStatus.APPLIED,  # Start with APPLIED
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
                    # This ensures _update_resume_employment_info is called properly
                    if target_status != ApplicationStatus.APPLIED:
                        application.status = target_status
                        application.save()  # This will trigger employment info update

                    applications.append(application)

                except Exception as e:
                    # Skip duplicates
                    logger.debug(f"Skipped application: {e}")
                    continue

        self.stdout.write(
            f"  Created {len(applications)} applications ({self.APPLICATION_START_DATE.date()} to {self.APPLICATION_END_DATE.date()})"
        )
        return applications

    def _generate_application_status(
            self, applied_at: datetime
    ) -> Tuple[str, Optional[datetime], Optional[datetime]]:
        """Generate a realistic application status with appropriate timestamps."""
        in_review_at = None
        hired_at = None

        # Random status distribution
        rand = random.random()

        if rand < 0.35:
            # 35% stay in APPLIED
            status = ApplicationStatus.APPLIED
        elif rand < 0.50:
            # 15% in INTERVIEW_SCHEDULED
            status = ApplicationStatus.INTERVIEW_SCHEDULED
            in_review_at = applied_at + timedelta(days=random.randint(1, 10))
        elif rand < 0.60:
            # 10% INTERVIEWED
            status = ApplicationStatus.INTERVIEWED
            in_review_at = applied_at + timedelta(days=random.randint(1, 10))
        elif rand < 0.70:
            # 10% REJECTED
            status = ApplicationStatus.REJECTED
            in_review_at = applied_at + timedelta(days=random.randint(1, 10))
        elif rand < 0.78:
            # 8% OFFERED
            status = ApplicationStatus.OFFERED
            in_review_at = applied_at + timedelta(days=random.randint(1, 10))
        elif rand < 0.85:
            # 7% OFFER_ACCEPTED (hired)
            status = ApplicationStatus.OFFER_ACCEPTED
            in_review_at = applied_at + timedelta(days=random.randint(1, 10))
            hired_at = in_review_at + timedelta(days=random.randint(3, 15))
        elif rand < 0.90:
            # 5% OFFER_REJECTED
            status = ApplicationStatus.OFFER_REJECTED
            in_review_at = applied_at + timedelta(days=random.randint(1, 10))
        else:
            # 10% WITHDRAWN
            status = ApplicationStatus.WITHDRAWN
            in_review_at = applied_at + timedelta(days=random.randint(1, 5))

        return status, in_review_at, hired_at

    def _create_vacancy_views(
            self,
            candidates: List[Candidate],
            vacancies: List[Vacancy],
    ) -> List[VacancyView]:
        """Create vacancy views with varied timestamps."""
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
                # View happens after vacancy creation but within our data range
                view_start = max(vacancy.created_at, self.DATA_START_DATE)
                view_end = self.DATA_END_DATE

                if view_start >= view_end:
                    continue

                viewed_at = self._get_random_timestamp(view_start, view_end)
                duration = random.randint(5, 300)  # 5 seconds to 5 minutes

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

        self.stdout.write(f"  Created {len(views)} vacancy views")
        return views

    def _show_summary(
            self,
            companies: List,
            candidates: List,
            vacancies: List,
            applications: List,
            views: List,
            resumes: List,
    ):
        """Show summary of created data."""
        self.stdout.write(self.style.SUCCESS("\n=== Data Generation Complete ==="))
        self.stdout.write(f"Companies:    {len(companies)}")
        self.stdout.write(f"Candidates:   {len(candidates)}")
        self.stdout.write(f"Vacancies:    {len(vacancies)}")
        self.stdout.write(f"Resumes:      {len(resumes)}")
        self.stdout.write(f"Applications: {len(applications)}")
        self.stdout.write(f"Views:        {len(views)}")

        # Show active/inactive vacancy count
        if vacancies:
            active_count = sum(1 for v in vacancies if v.is_active)
            inactive_count = len(vacancies) - active_count
            self.stdout.write("\nVacancy Status:")
            self.stdout.write(f"  - Active: {active_count}")
            self.stdout.write(f"  - Inactive (>1 month old): {inactive_count}")

        # Show status distribution
        if applications:
            self.stdout.write("\nApplication Status Distribution:")
            status_counts = {}
            for app in applications:
                status_counts[app.status] = status_counts.get(app.status, 0) + 1
            for status, count in sorted(status_counts.items()):
                self.stdout.write(f"  - {status}: {count}")

        # Show date ranges
        if vacancies:
            dates = [v.created_at for v in vacancies]
            self.stdout.write(f"\nVacancy date range: {min(dates).date()} to {max(dates).date()}")

        if resumes:
            dates = [r.created_at for r in resumes]
            self.stdout.write(f"Resume date range: {min(dates).date()} to {max(dates).date()}")

        if applications:
            dates = [a.applied_at for a in applications]
            self.stdout.write(f"Application date range: {min(dates).date()} to {max(dates).date()}")

        # Show embedding status
        embedded_vacancies = sum(1 for v in vacancies if v.is_embedded)
        embedded_resumes = sum(1 for r in resumes if r.is_embedded)
        self.stdout.write("\nEmbeddings:")
        self.stdout.write(f"  - Vacancies with embeddings: {embedded_vacancies}/{len(vacancies)}")
        self.stdout.write(f"  - Resumes with embeddings: {embedded_resumes}/{len(resumes)}")

        self.stdout.write(self.style.SUCCESS("\nDone! Test data generation completed successfully."))
