"""
Custom test runner that skips system checks during tests.

This avoids the ACCOUNT_LOGIN_METHODS system check from django-allauth
which requires ACCOUNT_EMAIL_REQUIRED = True (deprecated in newer versions).
"""

from django.test.runner import DiscoverRunner


class WorkXplorerTestRunner(DiscoverRunner):
    """Test runner that skips Django system checks."""

    def run_checks(self, databases):
        """
        Skip Django system checks during tests.

        This bypasses the allauth system check that requires
        ACCOUNT_EMAIL_REQUIRED = True when ACCOUNT_LOGIN_METHODS = {'email'}.
        """
        pass
