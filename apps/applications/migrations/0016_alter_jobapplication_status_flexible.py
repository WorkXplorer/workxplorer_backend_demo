from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0015_initialize_company_statuses'),
    ]

    operations = [
        migrations.AlterField(
            model_name='jobapplication',
            name='status',
            field=models.CharField(
                default='APPLIED',
                help_text='Current status of this application in the hiring process',
                max_length=50,
            ),
        ),
    ]
