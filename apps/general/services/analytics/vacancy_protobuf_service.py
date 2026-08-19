"""
Protobuf service for Vacancy analytics data.
Handles encoding and decoding of vacancy analytics data using compiled Protocol Buffers.

Vacancy data is now sent to a dedicated webhook endpoint, separate from company analytics.
"""

import logging
import json
from typing import Dict, Any

# Import the compiled vacancy protobuf module
try:
    from apps.general.services.analytics import vacancy_analytics_pb2
except ImportError:
    vacancy_analytics_pb2 = None
    logging.warning(
        "vacancy_analytics_pb2 not found. Run: "
        "cd apps/general/services/analytics && "
        "python -m grpc_tools.protoc -I. --python_out=. vacancy_analytics.proto"
    )

logger = logging.getLogger(__name__)


# Header for WorkXplorer vacancy protobuf messages
# Must match b'WKXP' used by the HR Analytics service decoder
WORKXPLORER_VACANCY_HEADER = b'WKXP'
VACANCY_PROTOBUF_VERSION = 1


class VacancyAnalyticsProtobufService:
    """
    Service for handling protobuf encoding and decoding of vacancy analytics data.
    Uses compiled protobuf messages for the dedicated vacancy webhook.
    """

    @staticmethod
    def _ensure_string(value: Any) -> str:
        """Safely convert any value to string."""
        if value is None:
            return ""
        if isinstance(value, dict):
            logger.warning(
                f"_ensure_string received a dict where a string was expected. "
                f"Extracting 'name' or 'id' key from: {value}"
            )
            return str(value.get('name', value.get('id', '')))
        return str(value)

    @staticmethod
    def _ensure_int(value: Any) -> int:
        """Safely convert any value to int."""
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _ensure_float(value: Any) -> float:
        """Safely convert any value to float."""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _ensure_bool(value: Any) -> bool:
        """Safely convert any value to bool."""
        if value is None:
            return False
        return bool(value)

    @staticmethod
    def _build_meta(meta_data: Dict[str, Any]) -> 'vacancy_analytics_pb2.VacancyMeta':
        """Build VacancyMeta protobuf message from dictionary."""
        meta = vacancy_analytics_pb2.VacancyMeta()
        meta.env = VacancyAnalyticsProtobufService._ensure_string(meta_data.get('env'))
        meta.company_id = VacancyAnalyticsProtobufService._ensure_string(meta_data.get('company_id'))
        meta.vacancy_id = VacancyAnalyticsProtobufService._ensure_string(meta_data.get('vacancy_id'))
        return meta

    @staticmethod
    def _build_vacancy_analytics(
            vacancy_data: Dict[str, Any]
    ) -> 'vacancy_analytics_pb2.VacancyAnalytics':
        """Build VacancyAnalytics protobuf message from dictionary."""
        svc = VacancyAnalyticsProtobufService
        vacancy = vacancy_analytics_pb2.VacancyAnalytics()

        # Basic info
        vacancy.id = svc._ensure_string(vacancy_data.get('id'))
        vacancy.title = svc._ensure_string(vacancy_data.get('title'))
        vacancy.domain = svc._ensure_string(vacancy_data.get('domain'))
        vacancy.domain_id = svc._ensure_string(vacancy_data.get('domain_id'))
        vacancy.created_at = svc._ensure_string(vacancy_data.get('created_at'))
        vacancy.updated_at = svc._ensure_string(vacancy_data.get('updated_at'))
        vacancy.created_by_email = svc._ensure_string(vacancy_data.get('created_by_email'))

        # Additional fields
        vacancy.employment_type = svc._ensure_string(vacancy_data.get('employment_type'))
        vacancy.employment_format = svc._ensure_string(vacancy_data.get('employment_format'))
        vacancy.company_address = svc._ensure_string(vacancy_data.get('company_address'))
        vacancy.is_active = svc._ensure_bool(vacancy_data.get('is_active'))
        vacancy.number_of_positions = svc._ensure_int(vacancy_data.get('number_of_positions'))
        vacancy.salary_min = svc._ensure_string(vacancy_data.get('salary_min'))
        vacancy.salary_max = svc._ensure_string(vacancy_data.get('salary_max'))
        vacancy.salary_currency = svc._ensure_string(vacancy_data.get('salary_currency'))

        # Build vacancy cards/metrics
        cards_data = vacancy_data.get('cards', {})
        vacancy.cards.CopyFrom(svc._build_vacancy_cards(cards_data))

        return vacancy

    @staticmethod
    def _build_vacancy_cards(
            cards_data: Dict[str, Any]
    ) -> 'vacancy_analytics_pb2.VacancyCards':
        """Build VacancyCards protobuf message from dictionary."""
        svc = VacancyAnalyticsProtobufService
        cards = vacancy_analytics_pb2.VacancyCards()

        # 1. Time to hire
        tth_data = cards_data.get('time_to_hire', {})
        cards.time_to_hire.hired_count = svc._ensure_int(tth_data.get('hired_count'))
        cards.time_to_hire.total_days_to_hire = svc._ensure_int(tth_data.get('total_days_to_hire'))

        for hire_record in tth_data.get('hire_records', []):
            record = cards.time_to_hire.hire_records.add()
            record.application_id = svc._ensure_string(hire_record.get('application_id'))
            record.applied_at = svc._ensure_string(hire_record.get('applied_at'))
            record.hired_at = svc._ensure_string(hire_record.get('hired_at'))
            record.days_to_hire = svc._ensure_int(hire_record.get('days_to_hire'))

        # 2. Conversion
        conv_data = cards_data.get('conversion', {})
        cards.conversion.total_applications = svc._ensure_int(conv_data.get('total_applications'))
        cards.conversion.total_hired = svc._ensure_int(conv_data.get('total_hired'))

        # 3. Views
        views_data = cards_data.get('views', {})
        cards.views.total_views = svc._ensure_int(views_data.get('total_views'))
        cards.views.unique_viewers = svc._ensure_int(views_data.get('unique_viewers'))

        # 4. Applications
        apps_data = cards_data.get('applications', {})
        cards.applications.count = svc._ensure_int(apps_data.get('count'))

        # 5. Average age
        age_data = cards_data.get('average_age', {})
        cards.average_age.applicants_with_age = svc._ensure_int(age_data.get('applicants_with_age'))
        cards.average_age.total_age_sum = svc._ensure_int(age_data.get('total_age_sum'))

        # 6. Response funnel
        funnel_data = cards_data.get('response_funnel', {})
        cards.response_funnel.views_count = svc._ensure_int(funnel_data.get('views_count'))
        cards.response_funnel.applications_count = svc._ensure_int(funnel_data.get('applications_count'))
        cards.response_funnel.invitations_count = svc._ensure_int(funnel_data.get('invitations_count'))
        cards.response_funnel.interviews_count = svc._ensure_int(funnel_data.get('interviews_count'))
        cards.response_funnel.offers_count = svc._ensure_int(funnel_data.get('offers_count'))

        # 7. Top skills
        skills_data = cards_data.get('top_skills', {})
        cards.top_skills.total_candidates = svc._ensure_int(skills_data.get('total_candidates'))
        cards.top_skills.total_candidates_with_skills = svc._ensure_int(
            skills_data.get('total_candidates_with_skills')
        )

        for skill_item in skills_data.get('skills', []):
            skill_msg = cards.top_skills.skills.add()
            skill_msg.skill_id = svc._ensure_string(skill_item.get('skill_id'))
            skill_msg.skill_name = svc._ensure_string(skill_item.get('skill_name'))
            skill_msg.candidates_count = svc._ensure_int(skill_item.get('candidates_count'))

        # 8. Candidates by region
        region_data = cards_data.get('candidates_by_region', {})
        cards.candidates_by_region.total_candidates = svc._ensure_int(
            region_data.get('total_candidates')
        )
        cards.candidates_by_region.candidates_with_region = svc._ensure_int(
            region_data.get('candidates_with_region')
        )
        cards.candidates_by_region.average_age = svc._ensure_float(
            region_data.get('average_age')
        )

        for region_item in region_data.get('regions', []):
            region_msg = cards.candidates_by_region.regions.add()
            region_msg.region_code = svc._ensure_string(region_item.get('region_code'))
            region_msg.region_name = svc._ensure_string(region_item.get('region_name'))
            region_msg.candidates_count = svc._ensure_int(region_item.get('candidates_count'))
            region_msg.average_age = svc._ensure_float(region_item.get('average_age'))

            for edupartner_item in region_item.get('edupartners', []):
                edupartner_msg = region_msg.edupartners.add()
                edupartner_msg.edupartner_name = svc._ensure_string(
                    edupartner_item.get('edupartner_name')
                )
                edupartner_msg.count = svc._ensure_int(edupartner_item.get('count'))

        return cards

    @staticmethod
    def encode_vacancy_data(vacancy_payload: Dict[str, Any]) -> bytes:
        """
        Encode vacancy analytics data dictionary to protobuf binary format.

        Args:
            vacancy_payload: Dictionary containing vacancy analytics data with keys:
                source, timestamp, meta, vacancy, analytics_timestamp

        Returns:
            bytes: Protobuf binary encoded data with WorkXplorer vacancy header

        Raises:
            RuntimeError: If protobuf module is not compiled
            Exception: If encoding fails
        """
        if vacancy_analytics_pb2 is None:
            raise RuntimeError(
                "Vacancy protobuf module not compiled. Run: "
                "cd apps/general/services/analytics && "
                "python -m grpc_tools.protoc -I. --python_out=. vacancy_analytics.proto"
            )

        try:
            svc = VacancyAnalyticsProtobufService
            message = vacancy_analytics_pb2.VacancyAnalyticsData()

            message.source = svc._ensure_string(vacancy_payload.get('source'))
            message.timestamp = svc._ensure_string(vacancy_payload.get('timestamp'))
            message.analytics_timestamp = svc._ensure_string(
                vacancy_payload.get('analytics_timestamp')
            )

            # Build nested messages
            message.meta.CopyFrom(svc._build_meta(vacancy_payload.get('meta', {})))
            message.vacancy.CopyFrom(
                svc._build_vacancy_analytics(vacancy_payload.get('vacancy', {}))
            )

            # Serialize to protobuf binary
            protobuf_binary = message.SerializeToString()

            # Add header for identification
            header = WORKXPLORER_VACANCY_HEADER
            version = bytes([VACANCY_PROTOBUF_VERSION])
            length = len(protobuf_binary).to_bytes(4, byteorder='little')

            final_binary = header + version + length + protobuf_binary

            # Log encoding stats
            json_size = len(
                json.dumps(vacancy_payload, ensure_ascii=False, default=str).encode('utf-8')
            )
            protobuf_size = len(final_binary)
            compression_ratio = (1 - protobuf_size / json_size) * 100 if json_size > 0 else 0

            logger.debug(
                f"Vacancy protobuf encoding: JSON {json_size} bytes -> Protobuf {protobuf_size} bytes "
                f"(compression: {compression_ratio:.1f}%)"
            )

            return final_binary

        except Exception as e:
            logger.error(f"Failed to encode vacancy analytics data to protobuf: {e}")
            raise

    @staticmethod
    def decode_vacancy_data(binary_data: bytes) -> Dict[str, Any]:
        """
        Decode protobuf binary data back to vacancy analytics dictionary.

        Args:
            binary_data: Protobuf binary encoded data with WorkXplorer vacancy header

        Returns:
            Dict[str, Any]: Decoded vacancy analytics data

        Raises:
            ValueError: If data format is invalid
            RuntimeError: If protobuf module is not compiled
        """
        if vacancy_analytics_pb2 is None:
            raise RuntimeError("Vacancy protobuf module not compiled")

        try:
            if len(binary_data) < 9:
                raise ValueError("Invalid vacancy protobuf data: too short")

            if binary_data[:4] != WORKXPLORER_VACANCY_HEADER:
                raise ValueError("Invalid vacancy protobuf data: bad header")

            version = binary_data[4]
            if version != VACANCY_PROTOBUF_VERSION:
                raise ValueError(
                    f"Unsupported vacancy protobuf version: {version}, "
                    f"expected: {VACANCY_PROTOBUF_VERSION}"
                )

            length = int.from_bytes(binary_data[5:9], byteorder='little')
            protobuf_data = binary_data[9:9 + length]

            message = vacancy_analytics_pb2.VacancyAnalyticsData()
            message.ParseFromString(protobuf_data)

            return VacancyAnalyticsProtobufService._message_to_dict(message)

        except Exception as e:
            logger.error(f"Failed to decode vacancy protobuf data: {e}")
            raise

    @staticmethod
    def _message_to_dict(
            message: 'vacancy_analytics_pb2.VacancyAnalyticsData',
    ) -> Dict[str, Any]:
        """Convert VacancyAnalyticsData protobuf message back to dictionary."""
        return {
            'source': message.source,
            'timestamp': message.timestamp,
            'analytics_timestamp': message.analytics_timestamp,
            'meta': {
                'env': message.meta.env,
                'company_id': message.meta.company_id,
                'vacancy_id': message.meta.vacancy_id,
            },
            'vacancy': VacancyAnalyticsProtobufService._vacancy_analytics_to_dict(
                message.vacancy
            ),
        }

    @staticmethod
    def _vacancy_analytics_to_dict(
            vacancy: 'vacancy_analytics_pb2.VacancyAnalytics',
    ) -> Dict[str, Any]:
        """Convert VacancyAnalytics message to dict."""
        return {
            'id': vacancy.id,
            'title': vacancy.title,
            'domain': vacancy.domain or None,
            'domain_id': vacancy.domain_id or None,
            'created_at': vacancy.created_at,
            'updated_at': vacancy.updated_at,
            'created_by_email': vacancy.created_by_email or None,
            'employment_type': vacancy.employment_type or None,
            'employment_format': vacancy.employment_format or None,
            'is_active': vacancy.is_active,
            'number_of_positions': vacancy.number_of_positions,
            'salary_min': vacancy.salary_min or None,
            'salary_max': vacancy.salary_max or None,
            'salary_currency': vacancy.salary_currency or None,
            'cards': VacancyAnalyticsProtobufService._vacancy_cards_to_dict(vacancy.cards),
        }

    @staticmethod
    def _vacancy_cards_to_dict(
            cards: 'vacancy_analytics_pb2.VacancyCards',
    ) -> Dict[str, Any]:
        """Convert VacancyCards message to dict."""
        return {
            'time_to_hire': {
                'hired_count': cards.time_to_hire.hired_count,
                'total_days_to_hire': cards.time_to_hire.total_days_to_hire,
                'hire_records': [
                    {
                        'application_id': r.application_id,
                        'applied_at': r.applied_at,
                        'hired_at': r.hired_at,
                        'days_to_hire': r.days_to_hire,
                    }
                    for r in cards.time_to_hire.hire_records
                ],
            },
            'conversion': {
                'total_applications': cards.conversion.total_applications,
                'total_hired': cards.conversion.total_hired,
            },
            'views': {
                'total_views': cards.views.total_views,
                'unique_viewers': cards.views.unique_viewers,
            },
            'applications': {
                'count': cards.applications.count,
            },
            'average_age': {
                'applicants_with_age': cards.average_age.applicants_with_age,
                'total_age_sum': cards.average_age.total_age_sum,
            },
            'response_funnel': {
                'views_count': cards.response_funnel.views_count,
                'applications_count': cards.response_funnel.applications_count,
                'invitations_count': cards.response_funnel.invitations_count,
                'interviews_count': cards.response_funnel.interviews_count,
                'offers_count': cards.response_funnel.offers_count,
            },
            'top_skills': {
                'total_candidates': cards.top_skills.total_candidates,
                'total_candidates_with_skills': cards.top_skills.total_candidates_with_skills,
                'skills': [
                    {
                        'skill_id': s.skill_id,
                        'skill_name': s.skill_name,
                        'candidates_count': s.candidates_count,
                    }
                    for s in cards.top_skills.skills
                ],
            },
            'candidates_by_region': {
                'total_candidates': cards.candidates_by_region.total_candidates,
                'candidates_with_region': cards.candidates_by_region.candidates_with_region,
                'average_age': cards.candidates_by_region.average_age,
                'regions': [
                    {
                        'region_code': r.region_code,
                        'region_name': r.region_name,
                        'candidates_count': r.candidates_count,
                        'average_age': r.average_age,
                        'edupartners': [
                            {
                                'edupartner_name': e.edupartner_name,
                                'count': e.count,
                            }
                            for e in r.edupartners
                        ],
                    }
                    for r in cards.candidates_by_region.regions
                ],
            },
        }

    @staticmethod
    def validate_vacancy_data(vacancy_payload: Dict[str, Any]) -> bool:
        """
        Validate vacancy analytics data structure before encoding.

        Args:
            vacancy_payload: Dictionary containing vacancy analytics data

        Returns:
            bool: True if valid, False otherwise
        """
        try:
            required_fields = ['source', 'timestamp', 'meta', 'vacancy']
            for field in required_fields:
                if field not in vacancy_payload:
                    logger.warning(f"Missing required vacancy field: {field}")
                    return False

            vacancy = vacancy_payload.get('vacancy', {})
            if not vacancy.get('id'):
                logger.warning("Missing vacancy.id")
                return False

            meta = vacancy_payload.get('meta', {})
            if not meta.get('vacancy_id'):
                logger.warning("Missing meta.vacancy_id")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating vacancy analytics data: {e}")
            return False
