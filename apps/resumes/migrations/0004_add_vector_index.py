from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("resumes", "0003_remove_resumeskill_combined_text_en_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS resume_embedding_ivfflat_idx 
                ON resumes_resume 
                USING ivfflat (embedding vector_cosine_ops) 
                WITH (lists = 100);
            """,
            reverse_sql="DROP INDEX IF EXISTS resume_embedding_ivfflat_idx;",
        ),
    ]
