import random
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.edupartners.models import EduPartner, EduPartnersType, Faculty
from apps.authentication.models import Candidate, Company, Recruiter
from apps.profiles.models import CandidateProfile, RecruiterProfile, CompanyProfile
from apps.domain.models import Domain
from apps.skills.models import Skill
from apps.vacancies.models import Vacancy, VacancySkill
from apps.resumes.models import Resume
from apps.applications.models import JobApplication
from apps.applications.models.choices import ApplicationStatus

# Import shared configuration
from utils.shared_test_data_config import (
    DOMAIN_NAMES as SHARED_DOMAIN_NAMES,
    DefaultConfig,
    get_data_start_date,
    get_data_end_date,
)

# ============================================================================
# FACULTY-DOMAIN MAPPING CONFIGURATION
# ============================================================================
# This mapping ensures that faculties are linked to appropriate domains
# and that job titles and skills match the faculty/domain context
# Note: Uses shared configuration for consistency

FACULTY_DOMAIN_MAPPING = {
    "Computer Science": {
        "domains": ["Information Technology"],
        "job_titles": [
            "Software Developer",
            "Frontend Developer",
            "Backend Developer",
            "Full Stack Developer",
            "DevOps Engineer",
            "System Administrator",
            "Mobile Developer",
            "Machine Learning Engineer",
            "Data Engineer",
            "Cloud Engineer",
            "Software Architect",
            "QA Engineer",
            "Cybersecurity Analyst",
        ],
        "skills": [
            "Python",
            "Java",
            "JavaScript",
            "React",
            "Django",
            "SQL",
            "Docker",
            "Git",
            "Linux",
            "AWS",
            "Node.js",
            "TypeScript",
            "PostgreSQL",
            "MongoDB",
            "Redis",
        ],
    },
    "Business Administration": {
        "domains": ["Business & Management", "Human Resources"],
        "job_titles": [
            "Business Analyst",
            "Project Manager",
            "Operations Manager",
            "Business Development Manager",
            "Administrative Manager",
            "Office Manager",
            "Executive Assistant",
            "Management Consultant",
            "Strategy Analyst",
            "Business Operations Specialist",
        ],
        "skills": [
            "Project Management",
            "Leadership",
            "Communication",
            "Strategic Planning",
            "Business Analysis",
            "Microsoft Office",
            "Team Management",
            "Process Improvement",
            "Budgeting",
            "Presentation Skills",
        ],
    },
    "Engineering": {
        "domains": ["Engineering"],
        "job_titles": [
            "Mechanical Engineer",
            "Civil Engineer",
            "Electrical Engineer",
            "Industrial Engineer",
            "Structural Engineer",
            "Quality Control Engineer",
            "Manufacturing Engineer",
            "Process Engineer",
            "Project Engineer",
            "Design Engineer",
        ],
        "skills": [
            "AutoCAD",
            "SolidWorks",
            "MATLAB",
            "Project Management",
            "Technical Drawing",
            "Problem Solving",
            "Quality Control",
            "Six Sigma",
            "Lean Manufacturing",
            "3D Modeling",
        ],
    },
    "Medicine": {
        "domains": ["Healthcare & Medicine"],
        "job_titles": [
            "Medical Officer",
            "Healthcare Administrator",
            "Clinical Research Coordinator",
            "Medical Lab Technician",
            "Healthcare Consultant",
            "Patient Care Coordinator",
            "Medical Records Specialist",
            "Pharmaceutical Sales Representative",
            "Health Informatics Specialist",
            "Medical Writer",
        ],
        "skills": [
            "Patient Care",
            "Medical Terminology",
            "Healthcare Management",
            "Clinical Research",
            "HIPAA Compliance",
            "Medical Documentation",
            "Emergency Response",
            "Pharmacology",
            "Healthcare IT",
            "Data Analysis",
        ],
    },
    "Law": {
        "domains": ["Legal & Compliance", "Human Resources"],
        "job_titles": [
            "Legal Assistant",
            "Paralegal",
            "Compliance Officer",
            "Contract Specialist",
            "Legal Researcher",
            "Corporate Counsel",
            "Regulatory Affairs Specialist",
            "Risk Analyst",
            "Legal Secretary",
            "IP Specialist",
        ],
        "skills": [
            "Legal Research",
            "Contract Analysis",
            "Compliance Management",
            "Risk Assessment",
            "Documentation",
            "Negotiation",
            "Corporate Law",
            "Intellectual Property",
            "Regulatory Compliance",
            "Legal Writing",
        ],
    },
    "Economics": {
        "domains": ["Finance & Banking", "Business & Management"],
        "job_titles": [
            "Financial Analyst",
            "Economist",
            "Investment Analyst",
            "Risk Manager",
            "Credit Analyst",
            "Treasury Analyst",
            "Budget Analyst",
            "Economic Researcher",
            "Portfolio Manager",
            "Banking Officer",
        ],
        "skills": [
            "Financial Modeling",
            "Data Analysis",
            "Excel",
            "Statistical Analysis",
            "Economics",
            "Accounting",
            "Forecasting",
            "Bloomberg Terminal",
            "Risk Analysis",
            "SQL",
        ],
    },
    "Design": {
        "domains": ["Design & Creative"],
        "job_titles": [
            "UI/UX Designer",
            "Graphic Designer",
            "Product Designer",
            "Visual Designer",
            "Brand Designer",
            "Motion Designer",
            "Web Designer",
            "Creative Director",
            "Design Lead",
            "Illustrator",
        ],
        "skills": [
            "Figma",
            "Adobe Photoshop",
            "Adobe Illustrator",
            "UI/UX Design",
            "Prototyping",
            "Design Thinking",
            "Typography",
            "Color Theory",
            "User Research",
            "Wireframing",
        ],
    },
    "Languages": {
        "domains": ["Education", "Marketing & Sales"],
        "job_titles": [
            "Translator",
            "Interpreter",
            "Content Writer",
            "Copywriter",
            "Language Teacher",
            "Localization Specialist",
            "Technical Writer",
            "Editor",
            "Communications Specialist",
            "PR Specialist",
        ],
        "skills": [
            "Translation",
            "Writing",
            "Editing",
            "Proofreading",
            "Content Creation",
            "SEO Writing",
            "Communication",
            "Research",
            "Localization",
            "Public Speaking",
        ],
    },
    "Marketing": {
        "domains": ["Marketing & Sales"],
        "job_titles": [
            "Marketing Manager",
            "Digital Marketing Specialist",
            "Social Media Manager",
            "Content Marketing Manager",
            "SEO Specialist",
            "Brand Manager",
            "Marketing Analyst",
            "Growth Hacker",
            "Email Marketing Specialist",
            "Performance Marketing Manager",
        ],
        "skills": [
            "Digital Marketing",
            "SEO",
            "Social Media Marketing",
            "Google Analytics",
            "Content Marketing",
            "Email Marketing",
            "PPC Advertising",
            "Marketing Automation",
            "A/B Testing",
            "Data Analysis",
        ],
    },
    "Human Resources": {
        "domains": ["Human Resources"],
        "job_titles": [
            "HR Manager",
            "HR Specialist",
            "Recruiter",
            "Talent Acquisition Specialist",
            "HR Business Partner",
            "Compensation Analyst",
            "Training Coordinator",
            "Employee Relations Specialist",
            "HR Generalist",
            "Payroll Specialist",
        ],
        "skills": [
            "Recruitment",
            "Employee Relations",
            "HRIS",
            "Performance Management",
            "Compensation & Benefits",
            "Training & Development",
            "Labor Law",
            "Conflict Resolution",
            "Onboarding",
            "Talent Management",
        ],
    },
}

# Company industry mapping for more realistic company names
COMPANY_INDUSTRIES = {
    "Information Technology": [
        "Tech Solutions",
        "Digital Systems",
        "Software Labs",
        "Code Factory",
        "Dev Studio",
        "Cloud Systems",
        "Data Solutions",
        "AI Innovations",
        "Cyber Tech",
        "Smart Systems",
    ],
    "Finance & Banking": [
        "Capital Group",
        "Investment Partners",
        "Financial Services",
        "Banking Solutions",
        "Wealth Management",
        "Credit Union",
        "Asset Management",
        "Finance Hub",
        "Money Matters",
        "Trust Services",
    ],
    "Healthcare & Medicine": [
        "Medical Center",
        "Health Solutions",
        "Care Plus",
        "Wellness Group",
        "Pharma Solutions",
        "BioTech Labs",
        "HealthTech",
        "MedServices",
        "CarePoint",
        "Vital Health",
    ],
    "Business & Management": [
        "Consulting Group",
        "Strategy Partners",
        "Management Solutions",
        "Business Hub",
        "Operations Plus",
        "Excellence Corp",
        "Growth Partners",
        "Success Strategies",
        "Prime Solutions",
        "Impact Group",
    ],
    "Marketing & Sales": [
        "Marketing Pro",
        "Brand Solutions",
        "Growth Agency",
        "Digital Agency",
        "Sales Force",
        "Market Leaders",
        "Ad Tech",
        "Creative Agency",
        "Promotion Plus",
        "Media Group",
    ],
    "Engineering": [
        "Engineering Solutions",
        "Tech Engineering",
        "Build Systems",
        "Industrial Tech",
        "Construct Plus",
        "Design Engineering",
        "Precision Works",
        "Structural Systems",
        "Mega Projects",
        "Infrastructure Corp",
    ],
    "Legal & Compliance": [
        "Legal Partners",
        "Law Associates",
        "Compliance Solutions",
        "Justice Group",
        "Legal Advisors",
        "Counsel Corp",
        "Risk Solutions",
        "Regulatory Group",
        "Legal Excellence",
        "Advisory Services",
    ],
    "Design & Creative": [
        "Creative Studio",
        "Design Lab",
        "Visual Works",
        "Art House",
        "Pixel Perfect",
        "Design Solutions",
        "Creative Hub",
        "Studio Works",
        "Digital Design",
        "Artisan Studio",
    ],
    "Education": [
        "Learning Hub",
        "EduTech Solutions",
        "Knowledge Partners",
        "Training Academy",
        "Skill Development",
        "Education Plus",
        "Learning Solutions",
        "Academic Partners",
        "Training Pro",
        "EdServices",
    ],
    "Human Resources": [
        "HR Solutions",
        "Talent Partners",
        "People First",
        "Workforce Solutions",
        "Staffing Plus",
        "Recruitment Pro",
        "HR Consulting",
        "Talent Management",
        "Employee Solutions",
        "HR Excellence",
    ],
}

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Creates comprehensive test data for EduPartner analytics with realistic faculty-domain mapping"

    # Date range constants (2026 to current date)
    DATA_START_DATE = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    DATA_END_DATE = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    # Application date range (same as data range)
    APPLICATION_START_DATE = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
    APPLICATION_END_DATE = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    def add_arguments(self, parser):
        parser.add_argument(
            "--universities",
            type=int,
            default=DefaultConfig.EDUPARTNER_UNIVERSITIES,
            help=f"Number of universities to create (default: {DefaultConfig.EDUPARTNER_UNIVERSITIES})",
        )
        parser.add_argument(
            "--students-per-university",
            type=int,
            default=DefaultConfig.EDUPARTNER_STUDENTS_PER_UNIVERSITY,
            help=f"Number of students per university (default: {DefaultConfig.EDUPARTNER_STUDENTS_PER_UNIVERSITY})",
        )
        parser.add_argument(
            "--companies",
            type=int,
            default=DefaultConfig.EDUPARTNER_COMPANIES,
            help=f"Number of companies to create (default: {DefaultConfig.EDUPARTNER_COMPANIES})",
        )
        parser.add_argument(
            "--vacancies-per-month",
            type=int,
            default=DefaultConfig.EDUPARTNER_VACANCIES_PER_MONTH,
            help=f"Number of vacancies to create per month (default: {DefaultConfig.EDUPARTNER_VACANCIES_PER_MONTH})",
        )
        parser.add_argument(
            "--applications-per-vacancy-min",
            type=int,
            default=DefaultConfig.EDUPARTNER_APPLICATIONS_PER_VACANCY_MIN,
            help=f"Minimum applications per vacancy (default: {DefaultConfig.EDUPARTNER_APPLICATIONS_PER_VACANCY_MIN})",
        )
        parser.add_argument(
            "--applications-per-vacancy-max",
            type=int,
            default=DefaultConfig.EDUPARTNER_APPLICATIONS_PER_VACANCY_MAX,
            help=f"Maximum applications per vacancy (default: {DefaultConfig.EDUPARTNER_APPLICATIONS_PER_VACANCY_MAX})",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing test data before creating new data (NOT enabled by default)",
        )
        parser.add_argument(
            "--incremental",
            action="store_true",
            help="Generate data only for missing days since last generation per university",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating data",
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

        self.stdout.write(
            self.style.SUCCESS("Starting comprehensive EduPartner analytics test data creation...")
        )
        self.stdout.write(f"Data generation period: {self.DATA_START_DATE.date()} to {self.DATA_END_DATE.date()}")
        self.stdout.write(f"Incremental mode: {options['incremental']}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDRY RUN MODE - No data will be created"))
            return

        if options["incremental"]:
            self._handle_incremental_generation(options)
            return

        if options["clear_existing"]:
            self.clear_existing_data()

        with transaction.atomic():
            # Create core data
            domains = self.create_domains()
            skills = self.create_skills()
            university_types = self.create_university_types()

            # Create universities with faculties (properly mapped to domains)
            universities = self.create_universities(
                options["universities"], university_types, domains
            )

            # Create students
            students = self.create_students(
                universities, options["students_per_university"]
            )

            # Create companies and recruiters (with domain-specific names)
            companies = self.create_companies(options["companies"], domains)

            # Create vacancies spread across months (Jan 2026 to now)
            vacancies = self.create_vacancies_by_month(
                companies,
                options["vacancies_per_month"],
                domains,
                skills,
            )

            # Create resumes for students
            self.create_resumes(students, skills)

            # Create applications with various statuses (10-25 per vacancy)
            self.create_applications(
                students,
                vacancies,
                options["applications_per_vacancy_min"],
                options["applications_per_vacancy_max"],
            )

        self.print_summary(universities, students, companies, vacancies)

    def _handle_incremental_generation(self, options):
        """Handle incremental data generation for missing days per university."""
        self.stdout.write(self.style.WARNING("Incremental generation mode"))

        # Get existing universities
        universities = list(EduPartner.objects.all())
        if not universities:
            self.stdout.write(self.style.ERROR("No universities found. Run without --incremental first."))
            return

        self.stdout.write(f"Found {len(universities)} existing universities")

        # For each university, find the last generation date and generate missing data
        for university in universities:
            self._generate_missing_data_for_university(university, options)

    def _generate_missing_data_for_university(self, university, options):
        """Generate missing data for a specific university."""
        # Find the last data generation date for this university
        # Look at the latest application, resume, or vacancy creation date
        last_application = JobApplication.objects.filter(
            candidate__edupartner=university
        ).order_by('-applied_at').first()

        last_vacancy = Vacancy.objects.filter(
            company__companyprofile__isnull=False
        ).order_by('-created_at').first()  # Approximate, as we don't have direct university link

        last_resume = Resume.objects.filter(
            candidate__edupartner=university
        ).order_by('-created_at').first()

        # Find the most recent activity date
        dates = []
        if last_application:
            dates.append(last_application.applied_at.date())
        if last_resume:
            dates.append(last_resume.created_at.date())
        if last_vacancy:
            dates.append(last_vacancy.created_at.date())

        if dates:
            last_generation_date = max(dates)
        else:
            last_generation_date = self.DATA_START_DATE.date()

        # Calculate missing days
        current_date = timezone.now().date()
        if last_generation_date >= current_date:
            self.stdout.write(f"  {university.name}: No missing days (last: {last_generation_date})")
            return

        missing_days = (current_date - last_generation_date).days
        self.stdout.write(
            f"  {university.name}: Generating {missing_days} missing days (from {last_generation_date + timedelta(days=1)})")

        # Generate minimal data for missing days
        self._generate_minimal_data_for_period(
            university,
            last_generation_date + timedelta(days=1),
            current_date,
            options
        )

    def _generate_minimal_data_for_period(self, university, start_date, end_date, options):
        """Generate minimal test data for a specific period."""
        # Generate very minimal data - just a few applications and maybe 1-2 vacancies per day
        companies = list(Company.objects.all()[:5])  # Use existing companies
        students = list(Candidate.objects.filter(edupartner=university)[:20])  # Use existing students
        domains = list(Domain.objects.all())
        skills = list(Skill.objects.all())

        if not companies or not students:
            self.stdout.write(f"    Skipping {university.name}: missing companies or students")
            return

        current_date = start_date
        data_created = 0

        while current_date <= end_date:
            # Create 1-2 vacancies per day (randomly)
            if random.random() < 0.3:  # 30% chance of vacancy creation
                company = random.choice(companies)
                domain = random.choice(domains)
                recruiter = getattr(company, 'recruiters', None)
                recruiter_instance = recruiter.first() if recruiter else None
                if not recruiter_instance:
                    # Try fallback: get any recruiter for this company
                    from apps.authentication.models import Recruiter
                    recruiter_instance = Recruiter.objects.filter(company=company).first()
                if not recruiter_instance:
                    self.stdout.write(f"    Skipping vacancy for {company.name}: no recruiter found")
                    current_date += timedelta(days=1)
                    continue
                # Create a simple vacancy
                random_time = timezone.make_aware(
                    datetime.combine(current_date, datetime.min.time()) +
                    timedelta(hours=random.randint(8, 18))
                )
                vacancy = Vacancy.objects.create(
                    title=f"Software Developer at {company.name}",
                    company=company,
                    domain=domain,
                    requirements="Generated for incremental data",
                    salary_min=1000000,
                    salary_max=3000000,
                    created_at=random_time,
                    created_by=recruiter_instance
                )
                # Add skills
                selected_skills = random.sample(skills, min(3, len(skills)))
                for skill in selected_skills:
                    VacancySkill.objects.get_or_create(
                        vacancy=vacancy,
                        skill=skill,
                        defaults={'minimum_years': random.randint(0, 3)}
                    )
                data_created += 1

            # Create 2-4 applications per day
            num_applications = random.randint(2, 4)
            available_vacancies = list(Vacancy.objects.all()[:10])

            for _ in range(num_applications):
                if not available_vacancies:
                    break

                student = random.choice(students)
                vacancy = random.choice(available_vacancies)

                # Check if application already exists
                if JobApplication.objects.filter(candidate=student, vacancy=vacancy).exists():
                    continue

                # Create application with simple status
                random_time = timezone.make_aware(
                    datetime.combine(current_date, datetime.min.time()) +
                    timedelta(hours=random.randint(9, 17))
                )

                status_choices = [
                    ApplicationStatus.APPLIED,
                    ApplicationStatus.REJECTED,
                ]
                status = random.choice(status_choices)

                JobApplication.objects.create(
                    candidate=student,
                    vacancy=vacancy,
                    applied_at=random_time,
                    status=status,
                )
                data_created += 1

            current_date += timedelta(days=1)

        self.stdout.write(f"    Created {data_created} items for {university.name}")

    def print_summary(self, universities, students, companies, vacancies):
        """Print a summary of created data"""
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("Successfully created EduPartner analytics test data!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Universities: {len(universities)}")
        self.stdout.write(f"  Students: {len(students)}")
        self.stdout.write(f"  Companies: {len(companies)}")
        self.stdout.write(f"  Vacancies: {len(vacancies)}")
        self.stdout.write(f"  Applications: {JobApplication.objects.count()}")
        self.stdout.write(f"  Resumes: {Resume.objects.count()}")
        self.stdout.write("\nApplication Status Distribution:")
        for status in ApplicationStatus:
            count = JobApplication.objects.filter(status=status).count()
            self.stdout.write(f"    {status.label}: {count}")
        self.stdout.write("=" * 60)

    def clear_existing_data(self):
        """Clear existing test data"""
        self.stdout.write("Clearing existing test data...")

        # Delete in order to avoid foreign key constraints
        JobApplication.objects.all().delete()
        Resume.objects.all().delete()
        VacancySkill.objects.all().delete()
        Vacancy.objects.all().delete()
        CandidateProfile.objects.all().delete()
        Candidate.objects.all().delete()
        RecruiterProfile.objects.all().delete()
        Recruiter.objects.all().delete()
        CompanyProfile.objects.all().delete()
        Company.objects.all().delete()
        Faculty.objects.all().delete()
        EduPartner.objects.all().delete()
        EduPartnersType.objects.all().delete()
        self.stdout.write(self.style.WARNING("Cleared existing test data"))

    def create_domains(self):
        """Create domains if they don't exist - uses shared configuration"""
        # Use shared domain names for consistency across both analytics systems
        domain_names = SHARED_DOMAIN_NAMES

        domains = {}
        for name in domain_names:
            domain, created = Domain.objects.get_or_create(
                name=name,
                defaults={"description": f"Domain for {name} related professions"},
            )
            domains[name] = domain
            if created:
                self.stdout.write(f"  Created domain: {name}")

        return domains

    def create_skills(self):
        """Create all skills from faculty mapping"""
        all_skills = set()
        for faculty_data in FACULTY_DOMAIN_MAPPING.values():
            all_skills.update(faculty_data["skills"])

        skills = {}
        for name in all_skills:
            skill, created = Skill.objects.get_or_create(
                name=name, defaults={"description": f"Professional skill in {name}"}
            )
            skills[name] = skill

        self.stdout.write(f"  Created/verified {len(skills)} skills")
        return skills

    def create_university_types(self):
        """Create university types"""
        type_names = ["University", "Institute", "College", "Academy"]

        types = []
        for name in type_names:
            edu_type, created = EduPartnersType.objects.get_or_create(name=name)
            types.append(edu_type)
            if created:
                self.stdout.write(f"  Created university type: {name}")

        return types

    def create_universities(self, count, university_types, domains):
        """Create universities with properly mapped faculties"""
        universities = []
        cities = ["Tashkent", "Samarkand", "Bukhara", "Andijan", "Namangan", "Fergana"]
        university_prefixes = [
            "National",
            "State",
            "International",
            "Central",
            "Technical",
            "Applied Sciences",
        ]

        for i in range(count):
            city = cities[i % len(cities)]
            prefix = random.choice(university_prefixes)

            university = EduPartner.objects.create(
                name=f"{prefix} University of {city}",
                edupartner_type=random.choice(university_types),
                country="Uzbekistan",
                city=city,
                website=f"https://{city.lower()}-university{i + 1}.uz",
                description=f"A prestigious educational institution in {city}",
                is_active=True,
            )
            universities.append(university)

            # Create 4-6 faculties per university with CORRECT domain mapping
            faculty_keys = list(FACULTY_DOMAIN_MAPPING.keys())
            num_faculties = random.randint(4, 6)
            selected_faculty_keys = random.sample(faculty_keys, min(num_faculties, len(faculty_keys)))

            for faculty_key in selected_faculty_keys:
                faculty_config = FACULTY_DOMAIN_MAPPING[faculty_key]
                # Get the PRIMARY domain for this faculty (first in the list)
                primary_domain_name = faculty_config["domains"][0]
                domain = domains.get(primary_domain_name)

                Faculty.objects.create(
                    name=f"Faculty of {faculty_key}",
                    description=f"Faculty dedicated to {faculty_key} studies at {university.name}",
                    edupartner=university,
                    domain=domain,
                    is_active=True,
                )

            self.stdout.write(
                f"  Created: {university.name} with {len(selected_faculty_keys)} faculties"
            )

        return universities

    def create_students(self, universities, students_per_university):
        """Create student candidates with realistic profiles"""
        students = []

        first_names_male = [
            "Akbar", "Bobur", "Dilshod", "Eldor", "Farrux", "Gofur", "Husan",
            "Islom", "Javlon", "Kamol", "Lochin", "Mahmud", "Nodir", "Otabek",
            "Pulat", "Qobil", "Rustam", "Sardor", "Temur", "Ulugbek", "Vali",
            "Yakub", "Zafar", "Aziz", "Bekzod", "Davron", "Erkin", "Farhod",
            "Jasur", "Kamoliddin", "Mirzo", "Nuriddin", "Olim", "Ravshan",
        ]
        first_names_female = [
            "Aisha", "Barno", "Dilfuza", "Elnora", "Farida", "Gulnora", "Hilola",
            "Iroda", "Jasmine", "Kamila", "Laylo", "Madina", "Nigora", "Ozoda",
            "Parvina", "Qunduz", "Roxana", "Sabina", "Tamara", "Umida", "Vasila",
            "Yulduz", "Zarina", "Aziza", "Dilnoza", "Feruza", "Gulchehra",
            "Malika", "Nargiza", "Shahlo", "Zilola", "Maftuna", "Sevara",
        ]
        last_names = [
            "Abdullaev", "Boboqulov", "Choriyev", "Davlatov", "Ergashev",
            "Fayzullaev", "Ganikhonov", "Hasanov", "Ismoilov", "Jurayev",
            "Karimov", "Latipov", "Mirzayev", "Normatov", "Olimov", "Pulatov",
            "Qodirov", "Rahimov", "Salimov", "Toshmurodov", "Usmonov",
            "Vohidov", "Xamidov", "Yusupov", "Zoirov", "Azimov", "Burkhonov",
            "Djumaev", "Eshonov", "Foziljonov", "Hakimov", "Ibrohimov",
        ]

        student_counter = 0
        for university in universities:
            faculties = list(university.faculties.all())
            if not faculties:
                continue

            for i in range(students_per_university):
                # 55% female, 45% male for realistic distribution
                is_female = random.random() < 0.55
                first_name = random.choice(first_names_female if is_female else first_names_male)
                last_name = random.choice(last_names)

                # Students aged 18-26 (born 1999-2007)
                birth_year = random.randint(1999, 2007)
                birth_month = random.randint(1, 12)
                birth_day = random.randint(1, 28)
                birth_date = datetime(birth_year, birth_month, birth_day).date()

                # Create unique email
                email_base = f'{first_name.lower()}.{last_name.lower()}'
                email = f'{email_base}.{student_counter}@student.edu.uz'

                faculty = random.choice(faculties)

                student = Candidate.objects.create(
                    email=email,
                    edupartner=university,
                    faculty=faculty,
                    date_of_birth=birth_date,
                    is_candidate=True,
                    is_active=True,
                )

                CandidateProfile.objects.create(
                    candidate=student,
                    full_name=f"{first_name} {last_name}",
                    candidate_email=email,
                )

                students.append(student)
                student_counter += 1

        self.stdout.write(f"  Created {len(students)} students across all universities")
        return students

    def create_companies(self, count, domains):
        """Create companies with domain-specific naming"""
        companies = []
        company_prefixes = ["Uzbek", "Tashkent", "Central Asian", "Global", "Premier", "Elite", "Pro", "Smart"]
        cities = ["Tashkent", "Samarkand", "Bukhara", "Andijan", "Namangan"]

        domain_list = list(domains.keys())

        for i in range(count):
            # Pick a domain for this company
            domain_name = domain_list[i % len(domain_list)]
            domain = domains[domain_name]

            # Get industry-specific suffixes
            industry_suffixes = COMPANY_INDUSTRIES.get(
                domain_name,
                ["Solutions", "Services", "Group", "Partners", "Corp"]
            )

            prefix = random.choice(company_prefixes)
            suffix = random.choice(industry_suffixes)
            company_name = f"{prefix} {suffix}"

            # Ensure unique name
            while Company.objects.filter(name=company_name).exists():
                company_name = f"{prefix} {suffix} {random.randint(1, 999)}"

            company = Company.objects.create(
                name=company_name,
                domain=domain,
                tin=f"30{i + 1:07d}",
                is_active=True,
            )

            CompanyProfile.objects.create(
                company=company,
                description=f"{company_name} is a leading company in {domain_name}.",
                address=f"{random.randint(1, 150)} {random.choice(['Main', 'Business', 'Commerce', 'Innovation'])} Street, {random.choice(cities)}",
                website=f'https://{company_name.lower().replace(" ", "")}.uz',
            )

            # Create recruiter for company
            recruiter = Recruiter.objects.create(
                email=f'hr{i}@{company_name.lower().replace(" ", "")}.uz',
                company=company,
                is_recruiter=True,
                is_active=True,
            )

            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"HR Manager {i + 1}",
                phone=f"+99890{random.randint(1000000, 9999999)}",
            )

            companies.append(company)

        self.stdout.write(f"  Created {len(companies)} companies with profiles")
        return companies

    def get_months_from_start_to_now(self):
        """Generate list of months from January 2025 to current date"""
        start_date = timezone.make_aware(datetime(2025, 1, 1))
        current_date = timezone.now()

        months = []
        current = start_date
        while current <= current_date:
            months.append(current)
            # Move to next month
            if current.month == 12:
                current = timezone.make_aware(datetime(current.year + 1, 1, 1))
            else:
                current = timezone.make_aware(datetime(current.year, current.month + 1, 1))

        return months

    def create_vacancies_by_month(self, companies, vacancies_per_month, domains, skills):
        """Create vacancies distributed across each month from Jan 2025 to now"""
        vacancies = []
        months = self.get_months_from_start_to_now()

        employment_types = ["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP"]
        employment_formats = ["ON_SITE", "REMOTE", "HYBRID"]

        self.stdout.write(f"  Creating vacancies for {len(months)} months (Jan 2026 to now)...")

        for month_date in months:
            # Vary the number of vacancies per month (realistic fluctuation)
            month_vacancy_count = random.randint(
                int(vacancies_per_month * 0.7),
                int(vacancies_per_month * 1.3)
            )

            for _ in range(month_vacancy_count):
                company = random.choice(companies)
                recruiter = company.recruiters.first()

                if not recruiter:
                    continue

                # Get company's domain for matching job titles
                company_domain_name = company.domain.name if company.domain else "Information Technology"

                # Find matching faculty config or use a default
                matching_faculty = None
                for faculty_key, faculty_config in FACULTY_DOMAIN_MAPPING.items():
                    if company_domain_name in faculty_config["domains"]:
                        matching_faculty = faculty_config
                        break

                if not matching_faculty:
                    matching_faculty = FACULTY_DOMAIN_MAPPING["Computer Science"]

                # Create vacancy with date in this month
                day_of_month = random.randint(1, 28)
                created_at = timezone.make_aware(
                    datetime(month_date.year, month_date.month, day_of_month,
                             random.randint(8, 18), random.randint(0, 59))
                )

                # Select job title from matching domain
                job_title = random.choice(matching_faculty["job_titles"])

                # Salary ranges based on employment type
                emp_type = random.choice(employment_types)
                if emp_type == "INTERNSHIP":
                    salary_min = Decimal(random.randint(200, 400)) * 100000
                    salary_max = Decimal(random.randint(400, 700)) * 100000
                else:
                    salary_min = Decimal(random.randint(400, 900)) * 100000
                    salary_max = Decimal(random.randint(900, 2000)) * 100000

                vacancy = Vacancy.objects.create(
                    created_by=recruiter,
                    title=job_title,
                    domain=company.domain,
                    company=company,
                    experience=random.randint(0, 5),
                    contact_email=f'jobs@{company.name.lower().replace(" ", "")}.uz',
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency="UZS",
                    employment_type=emp_type,
                    employment_format=random.choice(employment_formats),
                    about_us=f"At {company.name}, we are dedicated to excellence in {company_domain_name}. Join our dynamic team!",
                    requirements=f"We are looking for talented individuals with experience in {job_title} position. Strong communication skills and teamwork ability required.",
                    responsibilities=f"As a {job_title}, you will be responsible for key deliverables in your area of expertise. Collaboration with cross-functional teams is essential.",
                    is_active=True,
                    number_of_positions=random.randint(1, 4),
                )

                # Manually set created_at (since auto_now_add won't allow this)
                Vacancy.objects.filter(pk=vacancy.pk).update(created_at=created_at)
                vacancy.refresh_from_db()

                # Add matching skills to vacancy
                vacancy_skill_names = random.sample(
                    matching_faculty["skills"],
                    min(random.randint(3, 6), len(matching_faculty["skills"]))
                )
                for skill_name in vacancy_skill_names:
                    skill = skills.get(skill_name)
                    if skill:
                        VacancySkill.objects.create(
                            vacancy=vacancy,
                            skill=skill,
                            is_required=random.choice([True, False]),
                            minimum_years=random.randint(0, 3),
                            proficiency_level=random.choice(
                                ["BEGINNER", "INTERMEDIATE", "ADVANCED"]
                            ),
                        )

                vacancies.append(vacancy)

            self.stdout.write(
                f"    {month_date.strftime('%B %Y')}: {month_vacancy_count} vacancies created"
            )

        return vacancies

    def create_resumes(self, students, skills):
        """Create resumes for most students"""
        resumes_created = 0
        for student in students:
            # 85% of students have resumes
            if random.random() < 0.85:
                try:
                    profile = CandidateProfile.objects.get(candidate=student)
                    faculty = student.faculty

                    # Get skills matching the student's faculty
                    faculty_name = faculty.name.replace("Faculty of ", "") if faculty else "General"
                    FACULTY_DOMAIN_MAPPING.get(faculty_name, {})

                    Resume.objects.create(
                        candidate=student,
                        title=f"Resume - {profile.full_name}",
                        description=f"Motivated {faculty_name} student from {student.edupartner.name} seeking opportunities to apply academic knowledge in a professional setting.",
                        is_active=True,
                    )
                    resumes_created += 1
                except CandidateProfile.DoesNotExist:
                    continue

        self.stdout.write(f"  Created {resumes_created} resumes")

    def create_applications(self, students, vacancies, min_apps, max_apps):
        """Create job applications with realistic status progression and 10-25 per vacancy"""
        applications_created = 0

        # Get students with resumes
        students_with_resumes = [
            s for s in students if Resume.objects.filter(candidate=s).exists()
        ]

        if not students_with_resumes:
            self.stdout.write(self.style.ERROR("No students with resumes found!"))
            return 0

        self.stdout.write(f"  Creating applications ({min_apps}-{max_apps} per vacancy)...")

        # Status probability weights (more realistic funnel)
        # Applied (100%) -> In Review (60%) -> Interview (40%) -> Offer (15%) -> Hired (10%)
        status_weights = {
            ApplicationStatus.APPLIED: 25,  # 25% stay at applied
            ApplicationStatus.REJECTED: 20,  # 20% rejected early
            ApplicationStatus.INTERVIEW_SCHEDULED: 15,  # 15% scheduled for interview
            ApplicationStatus.INTERVIEWED: 15,  # 15% completed interview
            ApplicationStatus.OFFERED: 10,  # 10% received offer
            ApplicationStatus.OFFER_ACCEPTED: 8,  # 8% accepted (hired)
            ApplicationStatus.OFFER_REJECTED: 4,  # 4% rejected offer
            ApplicationStatus.WITHDRAWN: 3,  # 3% withdrew
        }
        status_list = list(status_weights.keys())
        weights = list(status_weights.values())

        for vacancy in vacancies:
            # Random number of applications per vacancy (10-25)
            num_applications = random.randint(min_apps, max_apps)

            # Get students who could apply (matching faculty/domain if possible)
            potential_applicants = list(students_with_resumes)
            random.shuffle(potential_applicants)

            applicants = potential_applicants[:num_applications]

            for student in applicants:
                # Skip if already applied
                if JobApplication.objects.filter(candidate=student, vacancy=vacancy).exists():
                    continue

                resume = Resume.objects.filter(candidate=student).first()
                if not resume:
                    continue

                # Application date should be after vacancy creation, within reasonable time
                vacancy_created = vacancy.created_at
                max_days_after = min(60, (timezone.now() - vacancy_created).days)
                if max_days_after <= 0:
                    max_days_after = 1

                applied_at = vacancy_created + timedelta(
                    days=random.randint(0, max_days_after),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                # Ensure applied_at is not in the future
                if applied_at > timezone.now():
                    applied_at = timezone.now() - timedelta(hours=random.randint(1, 48))

                # Randomly select status based on weights
                status = random.choices(status_list, weights=weights, k=1)[0]

                # Create application with APPLIED status first
                application = JobApplication.objects.create(
                    candidate=student,
                    vacancy=vacancy,
                    applied_at=applied_at,
                    resume_used=resume,
                    cover_letter=f"I am excited to apply for the {vacancy.title} position at {vacancy.company.name}. As a student from {student.edupartner.name}, I believe my skills and enthusiasm make me a strong candidate.",
                    is_active=True,
                    status=ApplicationStatus.APPLIED,  # Start with APPLIED
                )

                # Set realistic timestamps based on target status
                if status not in [ApplicationStatus.APPLIED]:
                    # Set in_review_at for applications that progressed
                    review_delay = timedelta(days=random.randint(1, 7))
                    in_review_at = applied_at + review_delay
                    if in_review_at <= timezone.now():
                        application.in_review_at = in_review_at

                if status == ApplicationStatus.OFFER_ACCEPTED:
                    # Set hired_at for accepted offers
                    hire_delay = timedelta(days=random.randint(14, 45))
                    hired_at = applied_at + hire_delay
                    if hired_at <= timezone.now():
                        application.hired_at = hired_at

                # Now transition to the target status if different from APPLIED
                # This ensures _update_resume_employment_info is called properly
                if status != ApplicationStatus.APPLIED:
                    application.status = status
                    application.save()  # This will trigger employment info update
                else:
                    application.save()
                applications_created += 1

        self.stdout.write(f"  Created {applications_created} applications")

        # Print status breakdown
        self.stdout.write("  Status distribution:")
        for status in ApplicationStatus:
            count = JobApplication.objects.filter(status=status).count()
            percentage = (count / applications_created * 100) if applications_created > 0 else 0
            self.stdout.write(f"    {status.label}: {count} ({percentage:.1f}%)")

        return applications_created
