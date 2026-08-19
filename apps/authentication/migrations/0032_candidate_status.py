from django.db import migrations, connection
from django.utils.timezone import now


def fix_and_backfill_candidate_progress(apps, schema_editor):
    """
    1. Convert onboarding_progress column from integer to JSONB
    2. Backfill it with onboarding data based on related objects
    """
    # Step 1: Convert the column type using raw SQL
    with connection.cursor() as cursor:
        # Drop the existing integer column and recreate as JSONB
        cursor.execute("""
            ALTER TABLE authentication_candidate
            DROP COLUMN onboarding_progress;
        """)
        cursor.execute("""
            ALTER TABLE authentication_candidate
            ADD COLUMN onboarding_progress JSONB DEFAULT '{}'::jsonb;
        """)

    # Step 2: Now backfill using Django ORM
    Candidate = apps.get_model("authentication", "Candidate")
    CandidateProfile = apps.get_model("profiles", "CandidateProfile")
    Resume = apps.get_model("resumes", "Resume")
    JobApplication = apps.get_model("applications", "JobApplication")

    timestamp = now().isoformat()

    # Pre-fetch IDs of candidates who have related objects
    profile_ids = set(
        CandidateProfile.objects.values_list("candidate_id", flat=True)
    )
    resume_ids = set(
        Resume.objects.values_list("candidate_id", flat=True)
    )
    applied_ids = set(
        JobApplication.objects.values_list("candidate_id", flat=True)
    )
    vault_ids = set(
        Candidate.objects.filter(is_vault_verified=True).values_list("id", flat=True)
    )

    # Process candidates one by one
    for candidate in Candidate.objects.all():
        progress = {}
        
        if candidate.id in profile_ids:
            progress["create_profile"] = timestamp
        if candidate.id in resume_ids:
            progress["create_resume"] = timestamp
        if candidate.id in applied_ids:
            progress["vacancy_apply"] = timestamp
        if candidate.id in vault_ids:
            progress["verify_vault"] = timestamp

        # Save if we found some progress
        if progress:
            candidate.onboarding_progress = progress
            candidate.save(update_fields=["onboarding_progress"])


def reverse_backfill(apps, schema_editor):
    """Reverse: reset onboarding_progress back to empty dict."""
    # No-op - we cannot distinguish backfilled from organically filled.
    pass



class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0031_alter_consentconfiguration_consent_type"),
        ("profiles", "0019_remove_date_of_birth_from_candidateprofile"),
        ("resumes", "0023_alter_resumelanguagecertificate_file_optional"),
        ("applications", "0012_alter_applicationdocument_title"),
    ]

    operations = [
        migrations.RunPython(
            fix_and_backfill_candidate_progress,
            reverse_backfill,
        ),
    ]