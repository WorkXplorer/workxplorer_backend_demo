from django.contrib.contenttypes.models import ContentType
from ..models.consent import UserConsent
from ..models.consent_config import ConsentConfiguration
import logging

logger = logging.getLogger(__name__)


class ConsentService:
    """Service for creating and managing consent records"""

    @staticmethod
    def _get_active_configs(entity_type, request=None):
        """Fetch active consent configs once per request when possible."""
        cache = None
        if request is not None:
            cache = getattr(request, "_active_consent_configs_cache", None)
            if cache and entity_type in cache:
                return cache[entity_type]

        configs = list(
            ConsentConfiguration.objects.filter(
                entity_type=entity_type,
                is_active=True,
            ).order_by("consent_type")
        )

        if request is not None:
            if cache is None:
                cache = {}
                setattr(request, "_active_consent_configs_cache", cache)
            cache[entity_type] = configs

        return configs

    @staticmethod
    def create_consents_for_entity(consenter, entity_type, ip_address, user_agent='', request=None):
        """
        Create all required consent records for an entity based on active configurations.
        
        Args:
            consenter: The entity giving consent (Candidate, Recruiter, or Company)
            entity_type: The type of entity ('candidate', 'recruiter', or 'company')
            ip_address: IP address of the requester
            user_agent: Browser/device user agent string
        
        Returns:
            List of created UserConsent objects
        
        Raises:
            ValueError: If no active consent configurations found for entity type
        """
        # Normalize user_agent to ensure it's never None
        user_agent = user_agent or ''
        
        # Log consent creation for debugging
        logger.info(
            f"Creating consents for {entity_type} (ID: {consenter.id}), "
            f"IP: {ip_address}, User-Agent length: {len(user_agent)}"
        )
        
        required_configs = ConsentService._get_active_configs(entity_type, request=request)

        if not required_configs:
            raise ValueError(
                f"No active consent configurations found for {entity_type}. "
                f"Please configure consents in Django admin first."
            )

        content_type = ContentType.objects.get_for_model(consenter)
        consenter_id = str(consenter.id)
        pending_consents = [
            UserConsent(
                content_type=content_type,
                object_id=consenter_id,
                consent_config=config,
                consent_type=config.consent_type,
                version=config.version,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            for config in required_configs
        ]

        # Single INSERT ... ON CONFLICT DO NOTHING significantly reduces
        # queries versus per-config get_or_create.
        if pending_consents:
            UserConsent.objects.bulk_create(
                pending_consents,
                ignore_conflicts=True,
            )

        return pending_consents

    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request"""
        if not request:
            return '0.0.0.0'

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return ip

    @staticmethod
    def validate_entity_type(entity_type, request=None):
        """
        Validate that the entity type is valid and has active consent configurations.
        
        Args:
            entity_type: 'candidate', 'recruiter', or 'company'
        
        Returns:
            tuple: (is_valid, error_message, required_consents_list)
        """
        # Validate entity type
        valid_types = ['candidate', 'recruiter', 'company']
        if entity_type not in valid_types:
            return False, f"Invalid entity type. Must be one of: {', '.join(valid_types)}", []

        required_configs = ConsentService._get_active_configs(entity_type, request=request)

        if not required_configs:
            return False, (
                f"No active consent configurations found for {entity_type}. "
                f"Please contact administrator."
            ), []

        # Return list of required consents for frontend display
        consents_list = [
            {
                'consent_type': config.consent_type,
                'version': config.version,
                'name': config.name,
                'description': config.description
            }
            for config in required_configs
        ]

        return True, None, consents_list

    @staticmethod
    def get_required_consents_for_display(entity_type, language='en'):
        """
        Get list of required consents for frontend display with localization.
        
        Args:
            entity_type: 'candidate', 'recruiter', or 'company'
            language: Language code ('uz', 'ru', 'en')
        
        Returns:
            List of consent configurations with localized names/descriptions
        """
        required_configs = ConsentService._get_active_configs(entity_type)

        return [
            {
                'consent_type': config.consent_type,
                'version': config.version,
                'name': config.get_localized_name(language),
                'description': config.get_localized_description(language),
            }
            for config in required_configs
        ]
