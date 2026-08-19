"""
Protobuf service for edupartner analytics data.
Handles encoding and decoding of analytics data using compiled Protocol Buffers.
"""

import logging
from typing import Dict, Any, List
import json

try:
    from apps.edupartners.services import analytics_pb2
except ImportError:
    analytics_pb2 = None
    logging.warning(
        "analytics_pb2 not found. Run: "
        "python -m grpc_tools.protoc -I. --python_out=. analytics.proto"
    )

logger = logging.getLogger(__name__)


# Header for WorkXplorer protobuf messages
WORKXPLORER_HEADER = b'WKXP'
PROTOBUF_VERSION = 4  # Version 4 - 9-card analytics (breaking: Cards field numbers 1-9 repurposed)


def extract_domain_name(domain_data: Any) -> str:
    if domain_data is None:
        return ""
    if isinstance(domain_data, dict):
        return str(domain_data.get("name", ""))
    if isinstance(domain_data, str):
        return domain_data
    return ""


class EduPartnerAnalyticsProtobufService:
    """
    Service for handling PURE protobuf encoding and decoding of edupartner analytics data.
    Uses compiled protobuf messages - NO JSON inside the binary.
    """

    @staticmethod
    def _ensure_string(value: Any) -> str:
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
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _ensure_float(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _build_cards(cards_data: Dict[str, Any]) -> 'analytics_pb2.Cards':
        """Build Cards protobuf message from dictionary (9 cards)."""
        cards = analytics_pb2.Cards()

        def set_metric(msg, data):
            msg.label = EduPartnerAnalyticsProtobufService._ensure_string(data.get('label'))
            msg.value = EduPartnerAnalyticsProtobufService._ensure_float(data.get('value'))

        set_metric(cards.source_students, cards_data.get('source_students', {}))
        set_metric(cards.registered, cards_data.get('registered', {}))
        set_metric(cards.active_30_days, cards_data.get('active_30_days', {}))
        set_metric(cards.resume_uploaded, cards_data.get('resume_uploaded', {}))
        set_metric(cards.profile_filled, cards_data.get('profile_filled', {}))
        set_metric(cards.assessment_passed, cards_data.get('assessment_passed', {}))

        # Graduate salary (with currency)
        salary = cards_data.get('graduate_salary', {})
        cards.graduate_salary.label = EduPartnerAnalyticsProtobufService._ensure_string(salary.get('label'))
        cards.graduate_salary.value = EduPartnerAnalyticsProtobufService._ensure_float(salary.get('value'))
        cards.graduate_salary.currency = EduPartnerAnalyticsProtobufService._ensure_string(
            salary.get('currency', 'UZS')
        )

        set_metric(cards.students_on_internships, cards_data.get('students_on_internships', {}))
        set_metric(cards.total_vacancies, cards_data.get('total_vacancies', {}))

        return cards

    @staticmethod
    def _build_industry_data(industry: Dict[str, Any]) -> 'analytics_pb2.IndustryData':
        """Build IndustryData protobuf message."""
        industry_data = analytics_pb2.IndustryData()
        industry_data.domain_id = EduPartnerAnalyticsProtobufService._ensure_string(industry.get('domain_id'))
        industry_data.domain_name = EduPartnerAnalyticsProtobufService._ensure_string(industry.get('domain_name'))

        for daily in industry.get('daily_data', []):
            daily_msg = industry_data.daily_data.add()
            daily_msg.date = EduPartnerAnalyticsProtobufService._ensure_string(daily.get('date'))
            daily_msg.positions = EduPartnerAnalyticsProtobufService._ensure_int(daily.get('positions'))

        for monthly in industry.get('monthly_data', []):
            monthly_msg = industry_data.monthly_data.add()
            monthly_msg.month = EduPartnerAnalyticsProtobufService._ensure_string(monthly.get('month'))
            monthly_msg.month_name = EduPartnerAnalyticsProtobufService._ensure_string(monthly.get('month_name'))
            monthly_msg.positions = EduPartnerAnalyticsProtobufService._ensure_int(monthly.get('positions'))

        return industry_data

    @staticmethod
    def _build_popular_industries(industries_data: Dict[str, List]) -> 'analytics_pb2.PopularIndustries':
        industries = analytics_pb2.PopularIndustries()

        for industry in industries_data.get('7_days', []):
            industries.seven_days.append(
                EduPartnerAnalyticsProtobufService._build_industry_data(industry)
            )

        for industry in industries_data.get('30_days', []):
            industries.thirty_days.append(
                EduPartnerAnalyticsProtobufService._build_industry_data(industry)
            )

        for industry in industries_data.get('12_months', []):
            industries.twelve_months.append(
                EduPartnerAnalyticsProtobufService._build_industry_data(industry)
            )

        return industries

    @staticmethod
    def _build_employed_graduates(graduates_data: Dict[str, Any]) -> 'analytics_pb2.EmployedGraduates':
        graduates = analytics_pb2.EmployedGraduates()
        graduates.total_graduates = EduPartnerAnalyticsProtobufService._ensure_int(
            graduates_data.get('total_graduates'))
        graduates.employed_count = EduPartnerAnalyticsProtobufService._ensure_int(graduates_data.get('employed_count'))
        graduates.employment_rate_percentage = EduPartnerAnalyticsProtobufService._ensure_float(
            graduates_data.get('employment_rate_percentage'))

        for status, count in graduates_data.get('by_status', {}).items():
            graduates.by_status[status] = EduPartnerAnalyticsProtobufService._ensure_int(count)

        return graduates

    @staticmethod
    def _build_hiring_funnel(funnel_data: Dict[str, Any]) -> 'analytics_pb2.HiringFunnel':
        funnel = analytics_pb2.HiringFunnel()
        funnel.resumes_created = EduPartnerAnalyticsProtobufService._ensure_int(funnel_data.get('resumes_created'))
        funnel.interviewed = EduPartnerAnalyticsProtobufService._ensure_int(funnel_data.get('interviewed'))
        funnel.offered = EduPartnerAnalyticsProtobufService._ensure_int(funnel_data.get('offered'))
        funnel.hired = EduPartnerAnalyticsProtobufService._ensure_int(funnel_data.get('hired'))

        rates = funnel_data.get('conversion_rates', {})
        funnel.conversion_rates.resume_to_interview = EduPartnerAnalyticsProtobufService._ensure_float(
            rates.get('resume_to_interview'))
        funnel.conversion_rates.interview_to_offer = EduPartnerAnalyticsProtobufService._ensure_float(
            rates.get('interview_to_offer'))
        funnel.conversion_rates.offer_to_hire = EduPartnerAnalyticsProtobufService._ensure_float(
            rates.get('offer_to_hire'))
        funnel.conversion_rates.overall_conversion = EduPartnerAnalyticsProtobufService._ensure_float(
            rates.get('overall_conversion'))

        return funnel

    @staticmethod
    def _build_top_company(company_data: Dict[str, Any]) -> 'analytics_pb2.TopCompany':
        company = analytics_pb2.TopCompany()
        company.company_id = EduPartnerAnalyticsProtobufService._ensure_string(company_data.get('company_id'))
        company.company_name = EduPartnerAnalyticsProtobufService._ensure_string(company_data.get('company_name'))
        company.hired_count = EduPartnerAnalyticsProtobufService._ensure_int(company_data.get('hired_count'))
        company.rank = EduPartnerAnalyticsProtobufService._ensure_int(company_data.get('rank'))
        return company

    @staticmethod
    def encode_analytics_data(analytics_data: Dict[str, Any]) -> bytes:
        if analytics_pb2 is None:
            raise RuntimeError(
                "Protobuf module not compiled. Run: "
                "python -m grpc_tools.protoc -I. --python_out=. analytics.proto"
            )

        try:
            message = analytics_pb2.AnalyticsData()

            message.edupartner_id = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('edupartner_id')
            )
            message.edupartner_name = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('edupartner_name')
            )
            message.faculty_id = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('faculty_id')
            )
            message.faculty_name = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('faculty_name')
            )
            message.faculty_domain = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('faculty_domain')
            )
            message.faculty_domain_id = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('faculty_domain_id')
            )
            message.timestamp = EduPartnerAnalyticsProtobufService._ensure_string(
                analytics_data.get('timestamp')
            )

            message.cards.CopyFrom(
                EduPartnerAnalyticsProtobufService._build_cards(
                    analytics_data.get('cards', {})
                )
            )

            message.popular_industries.CopyFrom(
                EduPartnerAnalyticsProtobufService._build_popular_industries(
                    analytics_data.get('popular_industries', {})
                )
            )

            message.employed_graduates.CopyFrom(
                EduPartnerAnalyticsProtobufService._build_employed_graduates(
                    analytics_data.get('employed_graduates', {})
                )
            )

            message.hiring_funnel.CopyFrom(
                EduPartnerAnalyticsProtobufService._build_hiring_funnel(
                    analytics_data.get('hiring_funnel', {})
                )
            )

            for company in analytics_data.get('top_companies_by_placements', []):
                message.top_companies_by_placements.append(
                    EduPartnerAnalyticsProtobufService._build_top_company(company)
                )

            protobuf_binary = message.SerializeToString()

            header = WORKXPLORER_HEADER
            version = bytes([PROTOBUF_VERSION])
            length = len(protobuf_binary).to_bytes(4, byteorder='little')

            final_binary = header + version + length + protobuf_binary

            json_size = len(json.dumps(analytics_data, ensure_ascii=False).encode('utf-8'))
            protobuf_size = len(final_binary)
            compression_ratio = (1 - protobuf_size / json_size) * 100 if json_size > 0 else 0

            logger.debug(
                f"PURE protobuf encoding: JSON {json_size} bytes -> Protobuf {protobuf_size} bytes "
                f"(compression: {compression_ratio:.1f}%)"
            )

            return final_binary

        except Exception as e:
            logger.error(f"Failed to encode analytics data to protobuf: {e}")
            raise

    @staticmethod
    def decode_analytics_data(binary_data: bytes) -> Dict[str, Any]:
        if analytics_pb2 is None:
            raise RuntimeError("Protobuf module not compiled")

        try:
            if len(binary_data) < 9:
                raise ValueError("Invalid protobuf data: too short")

            if binary_data[:4] != WORKXPLORER_HEADER:
                raise ValueError("Invalid protobuf data: bad header")

            version = binary_data[4]
            if version != PROTOBUF_VERSION:
                raise ValueError(f"Unsupported protobuf version: {version}")

            length = int.from_bytes(binary_data[5:9], byteorder='little')
            if length <= 0:
                raise ValueError("Invalid protobuf payload length")

            expected_size = 9 + length
            if len(binary_data) != expected_size:
                raise ValueError(
                    f"Invalid protobuf payload size: expected {expected_size}, got {len(binary_data)}"
                )

            protobuf_data = binary_data[9:expected_size]

            message = analytics_pb2.AnalyticsData()
            message.ParseFromString(protobuf_data)

            return EduPartnerAnalyticsProtobufService._message_to_dict(message)

        except Exception as e:
            logger.error(f"Failed to decode protobuf data: {e}")
            raise

    @staticmethod
    def _message_to_dict(message: 'analytics_pb2.AnalyticsData') -> Dict[str, Any]:
        """Convert protobuf message back to dictionary."""
        def get_metric(card_msg):
            return {
                'label': card_msg.label,
                'value': card_msg.value,
            }

        return {
            'edupartner_id': message.edupartner_id,
            'edupartner_name': message.edupartner_name,
            'faculty_id': message.faculty_id,
            'faculty_name': message.faculty_name,
            'faculty_domain': message.faculty_domain,
            'faculty_domain_id': message.faculty_domain_id,
            'timestamp': message.timestamp,
            'cards': {
                'source_students': get_metric(message.cards.source_students),
                'registered': get_metric(message.cards.registered),
                'active_30_days': get_metric(message.cards.active_30_days),
                'resume_uploaded': get_metric(message.cards.resume_uploaded),
                'profile_filled': get_metric(message.cards.profile_filled),
                'assessment_passed': get_metric(message.cards.assessment_passed),
                'graduate_salary': {
                    'label': message.cards.graduate_salary.label,
                    'value': message.cards.graduate_salary.value,
                    'currency': message.cards.graduate_salary.currency,
                },
                'students_on_internships': get_metric(message.cards.students_on_internships),
                'total_vacancies': get_metric(message.cards.total_vacancies),
            },
            'popular_industries': {
                '7_days': [
                    EduPartnerAnalyticsProtobufService._industry_to_dict(ind)
                    for ind in message.popular_industries.seven_days
                ],
                '30_days': [
                    EduPartnerAnalyticsProtobufService._industry_to_dict(ind)
                    for ind in message.popular_industries.thirty_days
                ],
                '12_months': [
                    EduPartnerAnalyticsProtobufService._industry_to_dict(ind)
                    for ind in message.popular_industries.twelve_months
                ],
            },
            'employed_graduates': {
                'total_graduates': message.employed_graduates.total_graduates,
                'employed_count': message.employed_graduates.employed_count,
                'employment_rate_percentage': message.employed_graduates.employment_rate_percentage,
                'by_status': dict(message.employed_graduates.by_status),
            },
            'hiring_funnel': {
                'resumes_created': message.hiring_funnel.resumes_created,
                'interviewed': message.hiring_funnel.interviewed,
                'offered': message.hiring_funnel.offered,
                'hired': message.hiring_funnel.hired,
                'conversion_rates': {
                    'resume_to_interview': message.hiring_funnel.conversion_rates.resume_to_interview,
                    'interview_to_offer': message.hiring_funnel.conversion_rates.interview_to_offer,
                    'offer_to_hire': message.hiring_funnel.conversion_rates.offer_to_hire,
                    'overall_conversion': message.hiring_funnel.conversion_rates.overall_conversion,
                },
            },
            'top_companies_by_placements': [
                {
                    'company_id': c.company_id,
                    'company_name': c.company_name,
                    'hired_count': c.hired_count,
                    'rank': c.rank,
                }
                for c in message.top_companies_by_placements
            ],
        }

    @staticmethod
    def _industry_to_dict(industry: 'analytics_pb2.IndustryData') -> Dict[str, Any]:
        return {
            'domain_id': industry.domain_id,
            'domain_name': industry.domain_name,
            'daily_data': [
                {'date': d.date, 'positions': d.positions}
                for d in industry.daily_data
            ],
            'monthly_data': [
                {'month': m.month, 'month_name': m.month_name, 'positions': m.positions}
                for m in industry.monthly_data
            ],
        }

    @staticmethod
    def validate_analytics_data(analytics_data: Dict[str, Any]) -> bool:
        try:
            required_fields = [
                'edupartner_id', 'edupartner_name', 'cards', 'popular_industries',
                'employed_graduates', 'hiring_funnel', 'top_companies_by_placements',
                'timestamp'
            ]

            for field in required_fields:
                if field not in analytics_data:
                    logger.warning(f"Missing required field: {field}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating analytics data: {e}")
            return False

    @staticmethod
    def get_encoding_info(analytics_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            json_str = json.dumps(analytics_data, ensure_ascii=False)
            json_size = len(json_str.encode('utf-8'))

            protobuf_data = EduPartnerAnalyticsProtobufService.encode_analytics_data(analytics_data)
            protobuf_size = len(protobuf_data)

            compression_ratio = (1 - protobuf_size / json_size) * 100 if json_size > 0 else 0

            return {
                'json_size_bytes': json_size,
                'protobuf_size_bytes': protobuf_size,
                'compression_ratio_percent': round(compression_ratio, 1),
                'size_reduction_bytes': json_size - protobuf_size,
                'efficiency_gain': f"{compression_ratio:.1f}% smaller",
                'format': 'Pure Protobuf Binary (v4)'
            }

        except Exception as e:
            logger.error(f"Error calculating protobuf encoding info: {e}")
            return {'error': str(e)}
