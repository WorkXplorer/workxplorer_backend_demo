import django.db.models.deletion
import utils.fields.uuid7_field
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("authentication", "0034_customuser_phone_customuser_phone_verified_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialIdentity",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                (
                    "id",
                    models.UUIDField(
                        default=utils.fields.uuid7_field.uuidv7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("provider", models.CharField(choices=[("google", "Google"), ("apple", "Apple")], max_length=10)),
                (
                    "subject",
                    models.CharField(
                        help_text="Provider's stable, opaque user identifier (Google 'sub' / Apple 'sub').",
                        max_length=255,
                    ),
                ),
                (
                    "email_at_link",
                    models.EmailField(
                        blank=True,
                        help_text="Email the provider reported at link time — display only, never an identity key.",
                        max_length=254,
                        null=True,
                    ),
                ),
                ("email_verified", models.BooleanField(default=False)),
                (
                    "apple_refresh_token_ciphertext",
                    models.TextField(
                        blank=True,
                        help_text="Envelope-encrypted Apple provider refresh token (Apple identities only). "
                                   "Used only for status checks and revocation on account deletion.",
                        null=True,
                    ),
                ),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "social identity",
                "verbose_name_plural": "social identities",
            },
        ),
        migrations.CreateModel(
            name="MobileSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=utils.fields.uuid7_field.uuidv7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("device_id", models.CharField(help_text="Client-generated installation UUID.", max_length=100)),
                ("platform", models.CharField(choices=[("ios", "iOS"), ("android", "Android")], max_length=10)),
                ("app_version", models.CharField(blank=True, max_length=20, null=True)),
                ("build_number", models.CharField(blank=True, max_length=20, null=True)),
                ("device_name", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "auth_method",
                    models.CharField(
                        choices=[("password", "Password"), ("google", "Google"), ("apple", "Apple")],
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("revoked", "Revoked")],
                        default="active",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "idle_expires_at",
                    models.DateTimeField(help_text="Reset to now + idle TTL on every successful refresh."),
                ),
                (
                    "absolute_expires_at",
                    models.DateTimeField(help_text="Hard cap from session creation — never extended."),
                ),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_reason", models.CharField(blank=True, max_length=50, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mobile_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "mobile session",
                "verbose_name_plural": "mobile sessions",
            },
        ),
        migrations.CreateModel(
            name="RefreshToken",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=utils.fields.uuid7_field.uuidv7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="authentication.refreshtoken",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="refresh_tokens",
                        to="authentication.mobilesession",
                    ),
                ),
            ],
            options={
                "verbose_name": "refresh token",
                "verbose_name_plural": "refresh tokens",
            },
        ),
        migrations.CreateModel(
            name="OAuthChallenge",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=utils.fields.uuid7_field.uuidv7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("provider", models.CharField(choices=[("google", "Google"), ("apple", "Apple")], max_length=10)),
                ("device_id", models.CharField(max_length=100)),
                ("nonce_digest", models.CharField(max_length=64)),
                ("state_digest", models.CharField(blank=True, max_length=64, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "OAuth challenge",
                "verbose_name_plural": "OAuth challenges",
            },
        ),
        migrations.AddIndex(
            model_name="mobilesession",
            index=models.Index(fields=["user", "status"], name="auth_mobses_user_id_status_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilesession",
            index=models.Index(fields=["idle_expires_at"], name="auth_mobses_idle_exp_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilesession",
            index=models.Index(fields=["absolute_expires_at"], name="auth_mobses_abs_exp_idx"),
        ),
        migrations.AddIndex(
            model_name="refreshtoken",
            index=models.Index(fields=["session", "used_at"], name="auth_reftok_session_used_idx"),
        ),
        migrations.AddIndex(
            model_name="oauthchallenge",
            index=models.Index(fields=["expires_at"], name="auth_oauthchal_exp_idx"),
        ),
        migrations.AddConstraint(
            model_name="socialidentity",
            constraint=models.UniqueConstraint(fields=("provider", "subject"), name="unique_provider_subject"),
        ),
        migrations.AddConstraint(
            model_name="socialidentity",
            constraint=models.UniqueConstraint(fields=("user", "provider"), name="unique_user_provider"),
        ),
    ]
