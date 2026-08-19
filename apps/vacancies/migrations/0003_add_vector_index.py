from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("vacancies", "0002_vacancy_combined_text_en_vacancy_embedding_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS vacancy_embedding_ivfflat_idx 
                ON vacancies_vacancy 
                USING ivfflat (embedding vector_cosine_ops) 
                WITH (lists = 100);
            """,
            reverse_sql="DROP INDEX IF EXISTS vacancy_embedding_ivfflat_idx;",
        ),
    ]
