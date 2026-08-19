"""
Shared Test Data Configuration for Analytics.

This module provides a single source of truth for test data used by both:
- EduPartner analytics test data generation
- HR analytics test data generation

All shared entities (universities, companies, domains, skills, etc.) are defined here
to ensure consistency across both analytics services.
"""

from datetime import datetime, timezone as dt_timezone
from typing import Dict, List, Any


# ============================================================================
# DATE CONFIGURATION
# ============================================================================

def get_data_start_date(year: int = 2026) -> datetime:
    """Get the start date for data generation."""
    return datetime(year, 1, 1, tzinfo=dt_timezone.utc)


def get_data_end_date() -> datetime:
    """Get the end date for data generation (current time)."""
    from django.utils import timezone
    return timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)


# ============================================================================
# DOMAIN CONFIGURATION
# ============================================================================

DOMAIN_NAMES = [
    "Information Technology",
    "Business & Management",
    "Engineering",
    "Healthcare & Medicine",
    "Finance & Banking",
    "Marketing & Sales",
    "Education",
    "Design & Creative",
    "Legal & Compliance",
    "Human Resources",
    "Manufacturing",
    "Logistics & Supply Chain",
]

# ============================================================================
# SKILL CONFIGURATION
# ============================================================================

SKILL_NAMES = [
    # IT Skills
    "Python", "Java", "JavaScript", "TypeScript", "React", "Vue.js", "Angular",
    "Django", "Flask", "FastAPI", "Node.js", "Express.js", "SQL", "PostgreSQL",
    "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
    "Git", "CI/CD", "Linux", "Network Administration",
    # Business Skills
    "Project Management", "Agile", "Scrum", "Leadership", "Communication",
    "Teamwork", "Problem Solving", "Critical Thinking", "Data Analysis",
    "Strategic Planning", "Business Analysis", "Microsoft Office", "Team Management",
    "Process Improvement", "Budgeting", "Presentation Skills",
    # Engineering Skills
    "AutoCAD", "SolidWorks", "MATLAB", "Technical Drawing", "Quality Control",
    "Six Sigma", "Lean Manufacturing", "3D Modeling",
    # Healthcare Skills
    "Patient Care", "Medical Terminology", "Healthcare Management", "Clinical Research",
    "HIPAA Compliance", "Medical Documentation", "Emergency Response", "Pharmacology",
    # Design Skills
    "Figma", "Adobe Photoshop", "Adobe Illustrator", "UI/UX Design", "Prototyping",
    "Design Thinking", "Typography", "Color Theory", "User Research", "Wireframing",
    # Marketing Skills
    "Digital Marketing", "SEO", "Social Media Marketing", "Google Analytics",
    "Content Marketing", "Email Marketing", "PPC Advertising", "Marketing Automation",
    "A/B Testing",
    # Data Science
    "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch",
    # Finance
    "Financial Modeling", "Excel", "Statistical Analysis", "Economics", "Accounting",
    "Forecasting", "Bloomberg Terminal", "Risk Analysis", "Power BI", "Tableau",
    # HR
    "Recruitment", "Employee Relations", "HRIS", "Performance Management",
    "Compensation & Benefits", "Training & Development", "Labor Law", "Conflict Resolution",
    "Onboarding", "Talent Management",
    # Legal
    "Legal Research", "Contract Analysis", "Compliance Management", "Risk Assessment",
    "Documentation", "Negotiation", "Corporate Law", "Intellectual Property",
    "Regulatory Compliance", "Legal Writing",
    # General
    "Translation", "Writing", "Editing", "Proofreading", "Content Creation",
    "SEO Writing", "Research", "Localization", "Public Speaking", "Sales",
]

# ============================================================================
# REAL COMPANY DATA (Used in both analytics systems)
# ============================================================================

REAL_COMPANIES = [
    {
        "name": "Safia",
        "domain": "Manufacturing",
        "tin": "301234567",
        "description": "Safia - yetakchi oziq-ovqat ishlab chiqarish kompaniyasi. Yuqori sifatli mahsulotlar va zamonaviy texnologiyalar.",
        "website": "https://safia.uz",
        "address": "Toshkent shahri, Mirzo Ulug'bek tumani, Buyuk Ipak Yo'li ko'chasi, 15-uy",
    },
    {
        "name": "Alif",
        "domain": "Finance & Banking",
        "tin": "302345678",
        "description": "Alif - zamonaviy fintech kompaniyasi. Innovatsion moliyaviy xizmatlar va raqamli to'lovlar.",
        "website": "https://alif.uz",
        "address": "Toshkent shahri, Sergeli tumani, Qatortol ko'chasi, 8-uy",
    },
]

IMAGINARY_COMPANIES = [
    {"name": "TechVista Solutions", "domain": "Information Technology"},
    {"name": "GreenField Agro", "domain": "Manufacturing"},
    {"name": "Urban Logistics", "domain": "Logistics & Supply Chain"},
    {"name": "MedCare Plus", "domain": "Healthcare & Medicine"},
    {"name": "EduBright Academy", "domain": "Education"},
    {"name": "Creative Studio UZ", "domain": "Design & Creative"},
    {"name": "BuildPro Construction", "domain": "Engineering"},
    {"name": "MarketGrow Agency", "domain": "Marketing & Sales"},
    {"name": "LegalEase Partners", "domain": "Legal & Compliance"},
    {"name": "TalentFirst HR", "domain": "Human Resources"},
]

# ============================================================================
# REAL UNIVERSITY DATA (Used in both analytics systems)
# ============================================================================

REAL_UNIVERSITIES = [
    {
        "name": "UTAS (University of Tashkent for Applied Sciences)",
        "short_name": "UTAS",
        "type": "University",
        "country": "Uzbekistan",
        "city": "Tashkent",
        "website": "https://utas.uz",
        "description": "Amaliy fanlar bo'yicha Toshkent universiteti - zamonaviy ta'lim va innovatsion tadqiqotlar markazi.",
        "faculties": [
            {"name": "Computer Science", "domain": "Information Technology"},
            {"name": "Business Administration", "domain": "Business & Management"},
            {"name": "Engineering", "domain": "Engineering"},
            {"name": "Digital Media & Design", "domain": "Design & Creative"},
        ],
    },
]

# ============================================================================
# IMAGINARY UNIVERSITY DATA (For EduPartner with more data)
# ============================================================================

IMAGINARY_UNIVERSITIES = [
    {
        "name": "National University of Tashkent",
        "type": "University",
        "country": "Uzbekistan",
        "city": "Tashkent",
        "website": "https://tashkent-university.uz",
        "description": "Prestijli davlat universiteti - zamonaviy ta'lim va ilmiy tadqiqotlar markazi.",
        "faculties": [
            {"name": "Computer Science", "domain": "Information Technology"},
            {"name": "Business Administration", "domain": "Business & Management"},
            {"name": "Engineering", "domain": "Engineering"},
            {"name": "Economics", "domain": "Finance & Banking"},
            {"name": "Law", "domain": "Legal & Compliance"},
        ],
    },
    {
        "name": "State University of Samarkand",
        "type": "University",
        "country": "Uzbekistan",
        "city": "Samarkand",
        "website": "https://samarkand-state.uz",
        "description": "Samarqand davlat universiteti - tarixiy shahar ta'lim markazi.",
        "faculties": [
            {"name": "Computer Science", "domain": "Information Technology"},
            {"name": "Medicine", "domain": "Healthcare & Medicine"},
            {"name": "Marketing", "domain": "Marketing & Sales"},
            {"name": "Languages", "domain": "Education"},
        ],
    },
    {
        "name": "International University of Bukhara",
        "type": "University",
        "country": "Uzbekistan",
        "city": "Bukhara",
        "website": "https://bukhara-int.uz",
        "description": "Buxoro xalqaro universiteti - zamonaviy ta'lim standarlarida.",
        "faculties": [
            {"name": "Business Administration", "domain": "Business & Management"},
            {"name": "Design", "domain": "Design & Creative"},
            {"name": "Human Resources", "domain": "Human Resources"},
        ],
    },
    {
        "name": "Technical University of Andijan",
        "type": "Institute",
        "country": "Uzbekistan",
        "city": "Andijan",
        "website": "https://andijan-tech.uz",
        "description": "Andijon texnika instituti - muhandislik ta'limi markazi.",
        "faculties": [
            {"name": "Engineering", "domain": "Engineering"},
            {"name": "Computer Science", "domain": "Information Technology"},
        ],
    },
    {
        "name": "Applied Sciences Academy of Namangan",
        "type": "Academy",
        "country": "Uzbekistan",
        "city": "Namangan",
        "website": "https://namangan-applied.uz",
        "description": "Namangan amaliy fanlar akademiyasi - amaliy ta'lim yetakchisi.",
        "faculties": [
            {"name": "Computer Science", "domain": "Information Technology"},
            {"name": "Business Administration", "domain": "Business & Management"},
            {"name": "Economics", "domain": "Finance & Banking"},
        ],
    },
]

# ============================================================================
# FACULTY-DOMAIN MAPPING (For EduPartner with detailed mapping)
# ============================================================================

FACULTY_DOMAIN_MAPPING: Dict[str, Dict[str, Any]] = {
    "Computer Science": {
        "domains": ["Information Technology"],
        "job_titles": [
            "Software Developer", "Frontend Developer", "Backend Developer",
            "Full Stack Developer", "DevOps Engineer", "System Administrator",
            "Mobile Developer", "Machine Learning Engineer", "Data Engineer",
            "Cloud Engineer", "Software Architect", "QA Engineer", "Cybersecurity Analyst",
        ],
        "skills": [
            "Python", "Java", "JavaScript", "React", "Django", "SQL", "Docker",
            "Git", "Linux", "AWS", "Node.js", "TypeScript", "PostgreSQL", "MongoDB", "Redis",
        ],
    },
    "Business Administration": {
        "domains": ["Business & Management", "Human Resources"],
        "job_titles": [
            "Business Analyst", "Project Manager", "Operations Manager",
            "Business Development Manager", "Administrative Manager", "Office Manager",
            "Executive Assistant", "Management Consultant", "Strategy Analyst",
        ],
        "skills": [
            "Project Management", "Leadership", "Communication", "Strategic Planning",
            "Business Analysis", "Microsoft Office", "Team Management", "Process Improvement",
            "Budgeting", "Presentation Skills",
        ],
    },
    "Engineering": {
        "domains": ["Engineering"],
        "job_titles": [
            "Mechanical Engineer", "Civil Engineer", "Electrical Engineer",
            "Industrial Engineer", "Structural Engineer", "Quality Control Engineer",
            "Manufacturing Engineer", "Process Engineer", "Project Engineer", "Design Engineer",
        ],
        "skills": [
            "AutoCAD", "SolidWorks", "MATLAB", "Project Management", "Technical Drawing",
            "Problem Solving", "Quality Control", "Six Sigma", "Lean Manufacturing", "3D Modeling",
        ],
    },
    "Medicine": {
        "domains": ["Healthcare & Medicine"],
        "job_titles": [
            "Medical Officer", "Healthcare Administrator", "Clinical Research Coordinator",
            "Medical Lab Technician", "Healthcare Consultant", "Patient Care Coordinator",
            "Medical Records Specialist", "Health Informatics Specialist", "Medical Writer",
        ],
        "skills": [
            "Patient Care", "Medical Terminology", "Healthcare Management", "Clinical Research",
            "HIPAA Compliance", "Medical Documentation", "Emergency Response", "Pharmacology",
            "Healthcare IT", "Data Analysis",
        ],
    },
    "Law": {
        "domains": ["Legal & Compliance", "Human Resources"],
        "job_titles": [
            "Legal Assistant", "Paralegal", "Compliance Officer", "Contract Specialist",
            "Legal Researcher", "Corporate Counsel", "Regulatory Affairs Specialist",
            "Risk Analyst", "Legal Secretary", "IP Specialist",
        ],
        "skills": [
            "Legal Research", "Contract Analysis", "Compliance Management", "Risk Assessment",
            "Documentation", "Negotiation", "Corporate Law", "Intellectual Property",
            "Regulatory Compliance", "Legal Writing",
        ],
    },
    "Economics": {
        "domains": ["Finance & Banking", "Business & Management"],
        "job_titles": [
            "Financial Analyst", "Economist", "Investment Analyst", "Risk Manager",
            "Credit Analyst", "Treasury Analyst", "Budget Analyst", "Economic Researcher",
            "Portfolio Manager", "Banking Officer",
        ],
        "skills": [
            "Financial Modeling", "Data Analysis", "Excel", "Statistical Analysis",
            "Economics", "Accounting", "Forecasting", "Bloomberg Terminal", "Risk Analysis", "SQL",
        ],
    },
    "Design": {
        "domains": ["Design & Creative"],
        "job_titles": [
            "UI/UX Designer", "Graphic Designer", "Product Designer", "Visual Designer",
            "Brand Designer", "Motion Designer", "Web Designer", "Creative Director",
            "Design Lead", "Illustrator",
        ],
        "skills": [
            "Figma", "Adobe Photoshop", "Adobe Illustrator", "UI/UX Design", "Prototyping",
            "Design Thinking", "Typography", "Color Theory", "User Research", "Wireframing",
        ],
    },
    "Digital Media & Design": {
        "domains": ["Design & Creative"],
        "job_titles": [
            "UI/UX Designer", "Graphic Designer", "Product Designer", "Visual Designer",
            "Brand Designer", "Motion Designer", "Web Designer", "Creative Director",
        ],
        "skills": [
            "Figma", "Adobe Photoshop", "Adobe Illustrator", "UI/UX Design", "Prototyping",
            "Design Thinking", "Typography", "Color Theory",
        ],
    },
    "Languages": {
        "domains": ["Education", "Marketing & Sales"],
        "job_titles": [
            "Translator", "Interpreter", "Content Writer", "Copywriter", "Language Teacher",
            "Localization Specialist", "Technical Writer", "Editor", "Communications Specialist",
        ],
        "skills": [
            "Translation", "Writing", "Editing", "Proofreading", "Content Creation",
            "SEO Writing", "Communication", "Research", "Localization", "Public Speaking",
        ],
    },
    "Marketing": {
        "domains": ["Marketing & Sales"],
        "job_titles": [
            "Marketing Manager", "Digital Marketing Specialist", "Social Media Manager",
            "Content Marketing Manager", "SEO Specialist", "Brand Manager", "Marketing Analyst",
            "Growth Hacker", "Email Marketing Specialist", "Performance Marketing Manager",
        ],
        "skills": [
            "Digital Marketing", "SEO", "Social Media Marketing", "Google Analytics",
            "Content Marketing", "Email Marketing", "PPC Advertising", "Marketing Automation",
            "A/B Testing", "Data Analysis",
        ],
    },
    "Human Resources": {
        "domains": ["Human Resources"],
        "job_titles": [
            "HR Manager", "HR Specialist", "Recruiter", "Talent Acquisition Specialist",
            "HR Business Partner", "Compensation Analyst", "Training Coordinator",
            "Employee Relations Specialist", "HR Generalist", "Payroll Specialist",
        ],
        "skills": [
            "Recruitment", "Employee Relations", "HRIS", "Performance Management",
            "Compensation & Benefits", "Training & Development", "Labor Law", "Conflict Resolution",
            "Onboarding", "Talent Management",
        ],
    },
}

# ============================================================================
# COMPANY INDUSTRY MAPPING (For dynamic company naming)
# ============================================================================

COMPANY_INDUSTRIES = {
    "Information Technology": [
        "Tech Solutions", "Digital Systems", "Software Labs", "Code Factory",
        "Dev Studio", "Cloud Systems", "Data Solutions", "AI Innovations",
        "Cyber Tech", "Smart Systems",
    ],
    "Finance & Banking": [
        "Capital Group", "Investment Partners", "Financial Services",
        "Banking Solutions", "Wealth Management", "Credit Union",
        "Asset Management", "Finance Hub", "Money Matters", "Trust Services",
    ],
    "Healthcare & Medicine": [
        "Medical Center", "Health Solutions", "Care Plus", "Wellness Group",
        "Pharma Solutions", "BioTech Labs", "HealthTech", "MedServices",
        "CarePoint", "Vital Health",
    ],
    "Business & Management": [
        "Consulting Group", "Strategy Partners", "Management Solutions",
        "Business Hub", "Operations Plus", "Excellence Corp", "Growth Partners",
        "Success Strategies", "Prime Solutions", "Impact Group",
    ],
    "Marketing & Sales": [
        "Marketing Pro", "Brand Solutions", "Growth Agency", "Digital Agency",
        "Sales Force", "Market Leaders", "Ad Tech", "Creative Agency",
        "Promotion Plus", "Media Group",
    ],
    "Engineering": [
        "Engineering Solutions", "Tech Engineering", "Build Systems",
        "Industrial Tech", "Construct Plus", "Design Engineering",
        "Precision Works", "Structural Systems", "Mega Projects", "Infrastructure Corp",
    ],
    "Legal & Compliance": [
        "Legal Partners", "Law Associates", "Compliance Solutions", "Justice Group",
        "Legal Advisors", "Counsel Corp", "Risk Solutions", "Regulatory Group",
        "Legal Excellence", "Advisory Services",
    ],
    "Design & Creative": [
        "Creative Studio", "Design Lab", "Visual Works", "Art House",
        "Pixel Perfect", "Design Solutions", "Creative Hub", "Studio Works",
        "Digital Design", "Artisan Studio",
    ],
    "Education": [
        "Learning Hub", "EduTech Solutions", "Knowledge Partners", "Training Academy",
        "Skill Development", "Education Plus", "Learning Solutions", "Academic Partners",
        "Training Pro", "EdServices",
    ],
    "Human Resources": [
        "HR Solutions", "Talent Partners", "People First", "Workforce Solutions",
        "Staffing Plus", "Recruitment Pro", "HR Consulting", "Talent Management",
        "Employee Solutions", "HR Excellence",
    ],
    "Manufacturing": [
        "Manufacturing Hub", "Production Plus", "Industrial Works", "Factory Systems",
        "Assembly Pro", "Quality Manufacturing", "Build Tech", "Precision Manufacturing",
    ],
    "Logistics & Supply Chain": [
        "Logistics Pro", "Supply Chain Solutions", "Transport Hub", "Delivery Systems",
        "Freight Solutions", "Distribution Network", "Cargo Tech", "Move Express",
    ],
}

# ============================================================================
# NAME DATA
# ============================================================================

FIRST_NAMES_MALE = [
    "Akbar", "Bobur", "Dilshod", "Eldor", "Farrux", "Gofur", "Husan",
    "Islom", "Javlon", "Kamol", "Lochin", "Mahmud", "Nodir", "Otabek",
    "Pulat", "Qobil", "Rustam", "Sardor", "Temur", "Ulugbek", "Vali",
    "Yakub", "Zafar", "Aziz", "Bekzod", "Davron", "Erkin", "Farhod",
    "Jasur", "Kamoliddin", "Mirzo", "Nuriddin", "Olim", "Ravshan",
]

FIRST_NAMES_FEMALE = [
    "Aisha", "Barno", "Dilfuza", "Elnora", "Farida", "Gulnora", "Hilola",
    "Iroda", "Jasmine", "Kamila", "Laylo", "Madina", "Nigora", "Ozoda",
    "Parvina", "Qunduz", "Roxana", "Sabina", "Tamara", "Umida", "Vasila",
    "Yulduz", "Zarina", "Aziza", "Dilnoza", "Feruza", "Gulchehra",
    "Malika", "Nargiza", "Shahlo", "Zilola", "Maftuna", "Sevara",
]

LAST_NAMES = [
    "Abdullaev", "Boboqulov", "Choriyev", "Davlatov", "Ergashev",
    "Fayzullaev", "Ganikhonov", "Hasanov", "Ismoilov", "Jurayev",
    "Karimov", "Latipov", "Mirzayev", "Normatov", "Olimov", "Pulatov",
    "Qodirov", "Rahimov", "Salimov", "Toshmurodov", "Usmonov",
    "Vohidov", "Xamidov", "Yusupov", "Zoirov", "Azimov", "Burkhonov",
    "Djumaev", "Eshonov", "Foziljonov", "Hakimov", "Ibrohimov",
]

CITIES = ["Tashkent", "Samarkand", "Bukhara", "Andijan", "Namangan", "Fergana", "Navoiy", "Xorazm"]

# ============================================================================
# MULTILINGUAL JOB TITLES AND DESCRIPTIONS
# ============================================================================

JOB_TITLES_MULTILINGUAL = [
    {"uz": "Dasturiy ta'minot muhandisi", "ru": "Инженер-программист", "en": "Software Engineer"},
    {"uz": "Frontend dasturchi", "ru": "Frontend разработчик", "en": "Frontend Developer"},
    {"uz": "Backend dasturchi", "ru": "Backend разработчик", "en": "Backend Developer"},
    {"uz": "Full Stack dasturchi", "ru": "Full Stack разработчик", "en": "Full Stack Developer"},
    {"uz": "Ma'lumotlar tahlilchisi", "ru": "Аналитик данных", "en": "Data Analyst"},
    {"uz": "Ma'lumotlar muhandisi", "ru": "Инженер данных", "en": "Data Engineer"},
    {"uz": "Loyiha menejeri", "ru": "Менеджер проекта", "en": "Project Manager"},
    {"uz": "Mahsulot menejeri", "ru": "Продуктовый менеджер", "en": "Product Manager"},
    {"uz": "DevOps muhandisi", "ru": "DevOps инженер", "en": "DevOps Engineer"},
    {"uz": "QA muhandisi", "ru": "QA инженер", "en": "QA Engineer"},
    {"uz": "UI/UX dizayner", "ru": "UI/UX дизайнер", "en": "UI/UX Designer"},
    {"uz": "Marketing menejeri", "ru": "Менеджер по маркетингу", "en": "Marketing Manager"},
    {"uz": "HR mutaxassisi", "ru": "HR специалист", "en": "HR Specialist"},
    {"uz": "Moliya tahlilchisi", "ru": "Финансовый аналитик", "en": "Financial Analyst"},
    {"uz": "Sotish menejeri", "ru": "Менеджер по продажам", "en": "Sales Manager"},
]

VACANCY_DESCRIPTIONS = {
    "about_us": {
        "uz": [
            "Biz innovatsion texnologiyalar sohasida faoliyat yurituvchi dinamik kompaniyamiz.",
            "Kompaniyamiz bozorda 10 yildan ortiq vaqtdan beri faoliyat yuritib kelmoqda.",
            "Biz tez rivojlanayotgan startapmiz va o'z sohamizda yetakchiga aylanishni maqsad qilganmiz.",
        ],
        "ru": [
            "Мы динамичная компания, работающая в сфере инновационных технологий.",
            "Наша компания работает на рынке более 10 лет.",
            "Мы быстрорастущий стартап, стремящийся стать лидером в своей отрасли.",
        ],
        "en": [
            "We are a dynamic company operating in innovative technologies.",
            "Our company has been operating in the market for over 10 years.",
            "We are a fast-growing startup aiming to become a leader in our industry.",
        ],
    },
    "requirements": {
        "uz": [
            "Kamida 2 yillik ish tajribasi. Tegishli texnologiyalar bo'yicha chuqur bilim.",
            "Oliy ma'lumot talab qilinadi. Ingliz tilini bilish afzallik.",
            "Kamida 3 yillik tajriba. O'z sohasida kuchli texnik bilimlar.",
        ],
        "ru": [
            "Минимум 2 года опыта работы. Глубокие знания соответствующих технологий.",
            "Требуется высшее образование. Знание английского языка приветствуется.",
            "Минимум 3 года опыта. Сильные технические знания в своей области.",
        ],
        "en": [
            "Minimum 2 years of experience. Deep knowledge of relevant technologies.",
            "Higher education required. English language knowledge is a plus.",
            "Minimum 3 years of experience. Strong technical knowledge in the field.",
        ],
    },
    "responsibilities": {
        "uz": [
            "Yangi loyihalarni ishlab chiqish va mavjud tizimlarni yaxshilash.",
            "Mijozlar bilan ishlash va ularning ehtiyojlarini aniqlash.",
            "Jamoani boshqarish va loyihalarni muddatida bajarish.",
        ],
        "ru": [
            "Разработка новых проектов и улучшение существующих систем.",
            "Работа с клиентами и определение их потребностей.",
            "Управление командой и своевременное выполнение проектов.",
        ],
        "en": [
            "Developing new projects and improving existing systems.",
            "Working with clients and identifying their needs.",
            "Managing the team and completing projects on time.",
        ],
    },
}

RESUME_DESCRIPTIONS = {
    "uz": [
        "Men tajribali {position} bo'lib, {years} yildan ortiq tajribaga egaman.",
        "Professional {position} sifatida turli sohalarda ish olib borganman.",
        "IT sohasida kuchli bilim va ko'nikmalarga ega mutaxassis.",
    ],
    "ru": [
        "Я опытный {position} с более чем {years} летним стажем.",
        "Как профессиональный {position}, работал в различных отраслях.",
        "Специалист с сильными знаниями и навыками в IT сфере.",
    ],
    "en": [
        "I am an experienced {position} with over {years} years of experience.",
        "As a professional {position}, I have worked in various industries.",
        "A specialist with strong knowledge and skills in IT.",
    ],
}


# ============================================================================
# DEFAULT CONFIGURATION VALUES
# ============================================================================

class DefaultConfig:
    """Default configuration values for test data generation."""

    # HR Analytics defaults (smaller dataset)
    HR_COMPANIES = 10
    HR_CANDIDATES = 100
    HR_VACANCIES_PER_COMPANY = 8

    # EduPartner defaults (larger dataset)
    EDUPARTNER_UNIVERSITIES = 5
    EDUPARTNER_STUDENTS_PER_UNIVERSITY = 100
    EDUPARTNER_COMPANIES = 30
    EDUPARTNER_VACANCIES_PER_MONTH = 15
    EDUPARTNER_APPLICATIONS_PER_VACANCY_MIN = 10
    EDUPARTNER_APPLICATIONS_PER_VACANCY_MAX = 25


def get_all_universities() -> List[Dict[str, Any]]:
    """Get all universities (real + imaginary) for EduPartner."""
    return REAL_UNIVERSITIES + IMAGINARY_UNIVERSITIES


def get_real_universities() -> List[Dict[str, Any]]:
    """Get only real universities (for HR Analytics)."""
    return REAL_UNIVERSITIES


def get_all_companies() -> List[Dict[str, Any]]:
    """Get all companies (real + imaginary)."""
    return REAL_COMPANIES + IMAGINARY_COMPANIES


def get_real_companies() -> List[Dict[str, Any]]:
    """Get only real companies."""
    return REAL_COMPANIES
