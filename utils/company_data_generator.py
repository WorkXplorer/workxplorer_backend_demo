"""
Company-Specific Data Generation Utilities.

This module provides helper functions for generating test data
for a specific company within a given date range.

These utilities are designed to be used by management commands
that need to generate isolated test data for a single company.
"""

import random
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from utils.shared_test_data_config import (
    FIRST_NAMES_MALE,
    FIRST_NAMES_FEMALE,
    LAST_NAMES,
    CITIES,
    JOB_TITLES_MULTILINGUAL,
    VACANCY_DESCRIPTIONS,
    RESUME_DESCRIPTIONS,
)


# ============================================================================
# DATE AND TIME UTILITIES
# ============================================================================


def generate_random_timestamp(
        start_date: datetime,
        end_date: datetime,
) -> datetime:
    """
    Generate a random timestamp within the specified date range.
    
    Args:
        start_date: The earliest possible datetime (inclusive).
        end_date: The latest possible datetime (inclusive).
        
    Returns:
        A random datetime between start_date and end_date.
    """
    if start_date >= end_date:
        return start_date

    time_delta = end_date - start_date
    random_seconds = random.randint(0, int(time_delta.total_seconds()))
    return start_date + timedelta(seconds=random_seconds)


def parse_date_string(date_str: str) -> datetime:
    """
    Parse a date string in YYYY-MM-DD format to a datetime object.
    
    Args:
        date_str: Date string in YYYY-MM-DD format.
        
    Returns:
        A datetime object with UTC timezone.
        
    Raises:
        ValueError: If the date string is not in the correct format.
    """
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)


def get_date_range_days(start_date: datetime, end_date: datetime) -> int:
    """
    Calculate the number of days between two dates.
    
    Args:
        start_date: The start date.
        end_date: The end date.
        
    Returns:
        The number of days between the two dates.
    """
    return max(0, (end_date - start_date).days)


# ============================================================================
# NAME AND IDENTITY GENERATION
# ============================================================================


def generate_random_name() -> Tuple[str, str, str]:
    """
    Generate a random full name.
    
    Returns:
        A tuple of (first_name, last_name, full_name).
    """
    first_names = FIRST_NAMES_MALE + FIRST_NAMES_FEMALE
    first_name = random.choice(first_names)
    last_name = random.choice(LAST_NAMES)
    full_name = f"{first_name} {last_name}"
    return first_name, last_name, full_name


def generate_unique_email(first_name: str, last_name: str, index: int, domain: str = "testmail.uz") -> str:
    """
    Generate a unique email address.
    
    Args:
        first_name: The first name.
        last_name: The last name.
        index: A unique index to ensure uniqueness.
        domain: The email domain (default: testmail.uz).
        
    Returns:
        A unique email address.
    """
    clean_first = first_name.lower().replace(" ", "").replace("'", "")
    clean_last = last_name.lower().replace(" ", "").replace("'", "")
    return f"{clean_first}.{clean_last}.{index}@{domain}"


def generate_phone_number() -> str:
    """
    Generate a random Uzbekistan phone number.
    
    Returns:
        A phone number string starting with +99890.
    """
    return f"+99890{random.randint(1000000, 9999999)}"


def generate_birth_date(min_age: int = 18, max_age: int = 35, reference_year: int = 2026) -> datetime:
    """
    Generate a random birth date for a person within the age range.
    
    Args:
        min_age: Minimum age in years.
        max_age: Maximum age in years.
        reference_year: The reference year for calculating age.
        
    Returns:
        A date object representing the birth date.
    """
    birth_year = random.randint(reference_year - max_age, reference_year - min_age)
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)  # Safe day range
    return datetime(birth_year, birth_month, birth_day).date()


# ============================================================================
# LANGUAGE AND CONTENT GENERATION
# ============================================================================


def get_random_language() -> str:
    """
    Get a random language code.
    
    Returns:
        One of 'uz', 'ru', or 'en'.
    """
    return random.choice(["uz", "ru", "en"])


def get_job_title(language: Optional[str] = None) -> Dict[str, str]:
    """
    Get a random job title with all language versions.
    
    Args:
        language: Optional specific language to filter by.
        
    Returns:
        A dictionary with 'uz', 'ru', 'en' keys and title values.
    """
    return random.choice(JOB_TITLES_MULTILINGUAL)


def get_vacancy_description(language: str, section: str) -> str:
    """
    Get a random vacancy description for a specific section and language.
    
    Args:
        language: Language code ('uz', 'ru', 'en').
        section: Description section ('about_us', 'requirements', 'responsibilities').
        
    Returns:
        A random description string.
    """
    sections = VACANCY_DESCRIPTIONS.get(section, {})
    descriptions = sections.get(language, sections.get("en", [""]))
    return random.choice(descriptions) if descriptions else ""


def get_resume_description(language: str, position: str, years: int) -> str:
    """
    Get a random resume description for the given language.
    
    Args:
        language: Language code ('uz', 'ru', 'en').
        position: The job position/title.
        years: Years of experience.
        
    Returns:
        A formatted resume description string.
    """
    descriptions = RESUME_DESCRIPTIONS.get(language, RESUME_DESCRIPTIONS.get("en", [""]))
    template = random.choice(descriptions) if descriptions else "{position} with {years} years experience"
    return template.format(position=position, years=years)


# ============================================================================
# APPLICATION STATUS GENERATION
# ============================================================================


# Status distribution weights for realistic simulation
APPLICATION_STATUS_DISTRIBUTION = {
    "APPLIED": 0.35,  # 35% stay in APPLIED
    "INTERVIEW_SCHEDULED": 0.15,  # 15% scheduled for interview
    "INTERVIEWED": 0.10,  # 10% interviewed
    "REJECTED": 0.10,  # 10% rejected
    "OFFERED": 0.08,  # 8% offered
    "OFFER_ACCEPTED": 0.07,  # 7% offer accepted (hired)
    "OFFER_REJECTED": 0.05,  # 5% offer rejected
    "WITHDRAWN": 0.10,  # 10% withdrawn
}


def generate_application_status(
        applied_at: datetime,
) -> Tuple[str, Optional[datetime], Optional[datetime]]:
    """
    Generate a realistic application status with appropriate timestamps.
    
    Args:
        applied_at: The datetime when the application was submitted.
        
    Returns:
        A tuple of (status, in_review_at, hired_at).
    """
    in_review_at = None
    hired_at = None

    rand = random.random()
    cumulative = 0.0

    for status, weight in APPLICATION_STATUS_DISTRIBUTION.items():
        cumulative += weight
        if rand <= cumulative:
            # Generate timestamps based on status
            if status in ["INTERVIEW_SCHEDULED", "INTERVIEWED", "REJECTED",
                          "OFFERED", "OFFER_ACCEPTED", "OFFER_REJECTED", "WITHDRAWN"]:
                in_review_at = applied_at + timedelta(days=random.randint(1, 10))

            if status == "OFFER_ACCEPTED":
                hired_at = in_review_at + timedelta(days=random.randint(3, 15)) if in_review_at else None

            return status, in_review_at, hired_at

    # Default to APPLIED if nothing matched
    return "APPLIED", None, None


# ============================================================================
# VACANCY GENERATION UTILITIES
# ============================================================================


EMPLOYMENT_TYPES = ["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP"]
EMPLOYMENT_FORMATS = ["ON_SITE", "REMOTE", "HYBRID"]
PROFICIENCY_LEVELS = ["BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"]
SALARY_CURRENCIES = ["UZS", "USD", "EUR"]


def generate_vacancy_data(
        language: str,
        created_at: datetime,
        inactive_threshold: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Generate random vacancy data.
    
    Args:
        language: Language code for content.
        created_at: The creation timestamp for the vacancy.
        inactive_threshold: Vacancies created before this date are marked inactive.
        
    Returns:
        A dictionary with vacancy field values.
    """
    job_title = get_job_title()

    is_active = True
    if inactive_threshold and created_at < inactive_threshold:
        is_active = False

    # Generate salary range
    salary_min = Decimal(random.randint(300, 800)) * 100000
    salary_max = Decimal(random.randint(800, 2000)) * 100000

    return {
        "title": job_title.get(language, job_title.get("en", "Developer")),
        "experience": random.randint(0, 7),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": "UZS",
        "employment_type": random.choice(EMPLOYMENT_TYPES),
        "employment_format": random.choice(EMPLOYMENT_FORMATS),
        "about_us": get_vacancy_description(language, "about_us"),
        "requirements": get_vacancy_description(language, "requirements"),
        "responsibilities": get_vacancy_description(language, "responsibilities"),
        "is_active": is_active,
        "number_of_positions": random.randint(1, 5),
    }


def select_random_skills(skills: List, min_count: int = 3, max_count: int = 8) -> List:
    """
    Select a random subset of skills.
    
    Args:
        skills: List of skill objects to choose from.
        min_count: Minimum number of skills to select.
        max_count: Maximum number of skills to select.
        
    Returns:
        A random subset of skills.
    """
    count = random.randint(min_count, min(max_count, len(skills)))
    return random.sample(skills, count) if skills else []


def generate_skill_data() -> Dict[str, Any]:
    """
    Generate random data for a skill association.
    
    Returns:
        A dictionary with skill association field values.
    """
    return {
        "is_required": random.choice([True, False]),
        "minimum_years": random.randint(0, 3),
        "proficiency_level": random.choice(PROFICIENCY_LEVELS),
    }


# ============================================================================
# RESUME GENERATION UTILITIES
# ============================================================================


WORK_STATUS_CHOICES = ["ACTIVELY_LOOKING", "OPEN_TO_OPPORTUNITIES", "NOT_LOOKING"]


def generate_resume_data(
        language: str,
        full_name: str,
) -> Dict[str, Any]:
    """
    Generate random resume data.
    
    Args:
        language: Language code for content.
        full_name: The candidate's full name.
        
    Returns:
        A dictionary with resume field values.
    """
    job_title = get_job_title()
    position = job_title.get(language, job_title.get("en", "Developer"))
    years_exp = random.randint(0, 10)

    return {
        "title": f"{full_name} - {position}",
        "position": position,
        "description": get_resume_description(language, position, years_exp),
        "work_status": random.choice(WORK_STATUS_CHOICES),
        "is_active": True,
        "is_main": True,
        "years_experience": years_exp,
    }


def generate_experience_data(language: str) -> Dict[str, Any]:
    """
    Generate random experience data.
    
    Args:
        language: Language code for content.
        
    Returns:
        A dictionary with experience field values.
    """
    exp_start_year = random.randint(2018, 2024)
    exp_start_month = random.randint(1, 12)
    exp_end_year = random.randint(exp_start_year, 2025)
    exp_end_month = random.randint(1, 12)

    job_title = get_job_title()

    return {
        "company": random.choice(["TechCorp", "StartupHub", "MegaSoft", "DataFlow", "CloudNine"]),
        "role": job_title.get(language, job_title.get("en", "Developer")),
        "country": "Uzbekistan",
        "city": random.choice(CITIES),
        "start_date": datetime(exp_start_year, exp_start_month, 1).date(),
        "end_date": datetime(exp_end_year, exp_end_month, 1).date() if random.random() > 0.3 else None,
        "description": "Worked as a professional in various projects.",
    }


# ============================================================================
# VACANCY VIEW GENERATION
# ============================================================================


def generate_view_duration() -> int:
    """
    Generate a random view duration in seconds.
    
    Returns:
        Duration between 5 seconds and 5 minutes.
    """
    return random.randint(5, 300)
