"""
Protobuf service for HR analytics data.
Handles encoding and decoding of analytics data using compiled Protocol Buffers.

This is a PURE protobuf implementation - no JSON inside.
"""

import logging
import json
from typing import Dict, Any
import math

# Import the compiled protobuf module
try:
    from apps.general.services.analytics import hr_analytics_pb2
except ImportError:
    hr_analytics_pb2 = None
    logging.warning(
        "hr_analytics_pb2 not found. Run: "
        "cd apps/general/services/analytics && "
        "python -m grpc_tools.protoc -I. --python_out=. hr_analytics.proto"
    )

logger = logging.getLogger(__name__)


# Header for WorkXplorer protobuf messages
WORKXPLORER_HEADER = b'WKXP'
HR_PROTOBUF_VERSION = 3  # Version 3 - Pure protobuf


def extract_optional_float(value: Any) -> float:
    """
    Extract optional float value, returning None for invalid values.
    
    Args:
        value: Value that might be a float, None, or invalid
        
    Returns:
        float or None
    """
    if value is None:
        return None
    try:
        float_val = float(value)
        # Check for JSON-incompatible floats
        if not math.isfinite(float_val):
            return None
        return float_val
    except (ValueError, TypeError):
        return None


class HRAnalyticsProtobufService:
    """
    Service for handling PURE protobuf encoding and decoding of HR analytics data.
    Uses compiled protobuf messages - NO JSON inside the binary.
    """

    @staticmethod
    def _ensure_string(value: Any) -> str:
        """
        Safely convert any value to string.
        
        Note: If a dictionary is passed, this method extracts the 'name' or 'id' key.
        This behavior is intentional but may indicate upstream data issues.
        A warning is logged when this conversion occurs.
        """
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
    def _build_meta(meta_data: Dict[str, Any]) -> 'hr_analytics_pb2.Meta':  # type: ignore
        """Build Meta protobuf message from dictionary."""
        meta = hr_analytics_pb2.Meta()
        meta.env = HRAnalyticsProtobufService._ensure_string(meta_data.get('env'))
        meta.company_id = HRAnalyticsProtobufService._ensure_string(meta_data.get('company_id'))
        return meta

    @staticmethod
    def _build_company(company_data: Dict[str, Any]) -> 'hr_analytics_pb2.Company':  # type: ignore
        """Build Company protobuf message from dictionary."""
        company = hr_analytics_pb2.Company()
        company.id = HRAnalyticsProtobufService._ensure_string(company_data.get('id'))
        company.name = HRAnalyticsProtobufService._ensure_string(company_data.get('name'))
        company.domain = HRAnalyticsProtobufService._ensure_string(company_data.get('domain'))
        company.tin = HRAnalyticsProtobufService._ensure_string(company_data.get('tin'))
        company.is_active = HRAnalyticsProtobufService._ensure_bool(company_data.get('is_active'))
        company.description = HRAnalyticsProtobufService._ensure_string(company_data.get('description'))
        company.address = HRAnalyticsProtobufService._ensure_string(company_data.get('address'))
        company.website = HRAnalyticsProtobufService._ensure_string(company_data.get('website'))
        company.photo = HRAnalyticsProtobufService._ensure_string(company_data.get('photo'))

        return company

    @staticmethod
    def _build_vacancy_analytics(vacancy_data: Dict[str, Any]) -> 'hr_analytics_pb2.VacancyAnalytics':  # type: ignore
        """Build VacancyAnalytics protobuf message from dictionary."""
        vacancy = hr_analytics_pb2.VacancyAnalytics()

        # Basic info
        vacancy.id = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('id'))
        vacancy.title = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('title'))
        vacancy.domain = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('domain'))
        vacancy.domain_id = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('domain_id'))
        vacancy.created_at = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('created_at'))
        vacancy.updated_at = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('updated_at'))
        vacancy.created_by_email = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('created_by_email'))

        # Additional fields
        vacancy.employment_type = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('employment_type'))
        vacancy.employment_format = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('employment_format'))
        vacancy.is_active = HRAnalyticsProtobufService._ensure_bool(vacancy_data.get('is_active'))
        vacancy.number_of_positions = HRAnalyticsProtobufService._ensure_int(vacancy_data.get('number_of_positions'))
        vacancy.salary_min = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('salary_min'))
        vacancy.salary_max = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('salary_max'))
        vacancy.salary_currency = HRAnalyticsProtobufService._ensure_string(vacancy_data.get('salary_currency'))

        # Build vacancy cards/metrics
        cards_data = vacancy_data.get('cards', {})
        vacancy.cards.CopyFrom(
            HRAnalyticsProtobufService._build_vacancy_cards(cards_data)
        )

        return vacancy

    @staticmethod
    def _build_vacancy_cards(cards_data: Dict[str, Any]) -> 'hr_analytics_pb2.VacancyCards':  # type: ignore
        """Build VacancyCards protobuf message from dictionary."""
        cards = hr_analytics_pb2.VacancyCards()

        # 1. Time to hire
        tth_data = cards_data.get('time_to_hire', {})
        cards.time_to_hire.hired_count = HRAnalyticsProtobufService._ensure_int(tth_data.get('hired_count'))
        cards.time_to_hire.total_days_to_hire = HRAnalyticsProtobufService._ensure_int(
            tth_data.get('total_days_to_hire'))

        for hire_record in tth_data.get('hire_records', []):
            record = cards.time_to_hire.hire_records.add()
            record.application_id = HRAnalyticsProtobufService._ensure_string(hire_record.get('application_id'))
            record.applied_at = HRAnalyticsProtobufService._ensure_string(hire_record.get('applied_at'))
            record.hired_at = HRAnalyticsProtobufService._ensure_string(hire_record.get('hired_at'))
            record.days_to_hire = HRAnalyticsProtobufService._ensure_int(hire_record.get('days_to_hire'))

        # 2. Conversion
        conv_data = cards_data.get('conversion', {})
        cards.conversion.total_applications = HRAnalyticsProtobufService._ensure_int(
            conv_data.get('total_applications'))
        cards.conversion.total_hired = HRAnalyticsProtobufService._ensure_int(conv_data.get('total_hired'))

        # 3. Views
        views_data = cards_data.get('views', {})
        cards.views.total_views = HRAnalyticsProtobufService._ensure_int(views_data.get('total_views'))
        cards.views.unique_viewers = HRAnalyticsProtobufService._ensure_int(views_data.get('unique_viewers'))

        # 4. Applications
        apps_data = cards_data.get('applications', {})
        cards.applications.count = HRAnalyticsProtobufService._ensure_int(apps_data.get('count'))

        # 5. Average age
        age_data = cards_data.get('average_age', {})
        cards.average_age.applicants_with_age = HRAnalyticsProtobufService._ensure_int(
            age_data.get('applicants_with_age'))
        cards.average_age.total_age_sum = HRAnalyticsProtobufService._ensure_int(age_data.get('total_age_sum'))

        # 6. Response funnel
        funnel_data = cards_data.get('response_funnel', {})
        cards.response_funnel.views_count = HRAnalyticsProtobufService._ensure_int(funnel_data.get('views_count'))
        cards.response_funnel.applications_count = HRAnalyticsProtobufService._ensure_int(
            funnel_data.get('applications_count'))
        cards.response_funnel.invitations_count = HRAnalyticsProtobufService._ensure_int(
            funnel_data.get('invitations_count'))
        cards.response_funnel.interviews_count = HRAnalyticsProtobufService._ensure_int(
            funnel_data.get('interviews_count'))
        cards.response_funnel.offers_count = HRAnalyticsProtobufService._ensure_int(funnel_data.get('offers_count'))

        # 7. Top skills
        skills_data = cards_data.get('top_skills', {})
        cards.top_skills.total_candidates = HRAnalyticsProtobufService._ensure_int(skills_data.get('total_candidates'))
        cards.top_skills.total_candidates_with_skills = HRAnalyticsProtobufService._ensure_int(
            skills_data.get('total_candidates_with_skills'))

        for skill_item in skills_data.get('skills', []):
            skill_msg = cards.top_skills.skills.add()
            skill_msg.skill_id = HRAnalyticsProtobufService._ensure_string(skill_item.get('skill_id'))
            skill_msg.skill_name = HRAnalyticsProtobufService._ensure_string(skill_item.get('skill_name'))
            skill_msg.candidates_count = HRAnalyticsProtobufService._ensure_int(skill_item.get('candidates_count'))

        # 8. Candidates by region
        region_data = cards_data.get('candidates_by_region', {})
        cards.candidates_by_region.total_candidates = HRAnalyticsProtobufService._ensure_int(
            region_data.get('total_candidates'))
        cards.candidates_by_region.candidates_with_region = HRAnalyticsProtobufService._ensure_int(
            region_data.get('candidates_with_region'))
        cards.candidates_by_region.average_age = HRAnalyticsProtobufService._ensure_float(
            region_data.get('average_age'))

        for region_item in region_data.get('regions', []):
            region_msg = cards.candidates_by_region.regions.add()
            region_msg.region_code = HRAnalyticsProtobufService._ensure_string(region_item.get('region_code'))
            region_msg.region_name = HRAnalyticsProtobufService._ensure_string(region_item.get('region_name'))
            region_msg.candidates_count = HRAnalyticsProtobufService._ensure_int(region_item.get('candidates_count'))
            region_msg.average_age = HRAnalyticsProtobufService._ensure_float(region_item.get('average_age'))

            # Add edupartners for this region
            for edupartner_item in region_item.get('edupartners', []):
                edupartner_msg = region_msg.edupartners.add()
                edupartner_msg.edupartner_name = HRAnalyticsProtobufService._ensure_string(
                    edupartner_item.get('edupartner_name'))
                edupartner_msg.count = HRAnalyticsProtobufService._ensure_int(edupartner_item.get('count'))

        return cards

    @staticmethod
    def _build_cards(cards_data: Dict[str, Any]) -> 'hr_analytics_pb2.Cards':  # type: ignore
        """Build Cards protobuf message from dictionary."""
        cards = hr_analytics_pb2.Cards()

        # Card 1: Average View Time
        avg_view = cards_data.get('average_view_time', {})
        cards.average_view_time.value = HRAnalyticsProtobufService._ensure_float(avg_view.get('value'))
        cards.average_view_time.unit = HRAnalyticsProtobufService._ensure_string(avg_view.get('unit', 'seconds'))
        cards.average_view_time.label = HRAnalyticsProtobufService._ensure_string(avg_view.get('label'))
        cards.average_view_time.total_views = HRAnalyticsProtobufService._ensure_int(avg_view.get('total_views'))

        # Card 2: Open Vacancies
        open_vac = cards_data.get('open_vacancies', {})
        cards.open_vacancies.value = HRAnalyticsProtobufService._ensure_int(open_vac.get('value'))
        cards.open_vacancies.label = HRAnalyticsProtobufService._ensure_string(open_vac.get('label'))
        pct_change = extract_optional_float(open_vac.get('percentage_change'))
        if pct_change is not None:
            cards.open_vacancies.percentage_change = pct_change

        # Card 3: Applications Count
        apps_count = cards_data.get('applications_count', {})
        cards.applications_count.value = HRAnalyticsProtobufService._ensure_int(apps_count.get('value'))
        cards.applications_count.label = HRAnalyticsProtobufService._ensure_string(apps_count.get('label'))
        pct_change = extract_optional_float(apps_count.get('percentage_change'))
        if pct_change is not None:
            cards.applications_count.percentage_change = pct_change

        # Card 4: Vacancy Views
        vac_views = cards_data.get('vacancy_views', {})
        cards.vacancy_views.value = HRAnalyticsProtobufService._ensure_int(vac_views.get('value'))
        cards.vacancy_views.label = HRAnalyticsProtobufService._ensure_string(vac_views.get('label'))
        pct_change = extract_optional_float(vac_views.get('percentage_change'))
        if pct_change is not None:
            cards.vacancy_views.percentage_change = pct_change
        cards.vacancy_views.unique_viewers = HRAnalyticsProtobufService._ensure_int(vac_views.get('unique_viewers'))

        # Card 5: Average Candidate Age
        avg_age = cards_data.get('average_candidate_age', {})
        age_value = extract_optional_float(avg_age.get('value'))
        if age_value is not None:
            cards.average_candidate_age.value = age_value
        cards.average_candidate_age.unit = HRAnalyticsProtobufService._ensure_string(avg_age.get('unit', 'years'))
        cards.average_candidate_age.label = HRAnalyticsProtobufService._ensure_string(avg_age.get('label'))
        age_change = extract_optional_float(avg_age.get('age_change'))
        if age_change is not None:
            cards.average_candidate_age.age_change = age_change

        return cards

    @staticmethod
    def _build_top_industries(industries_data: Dict[str, Any]) -> 'hr_analytics_pb2.TopIndustries':  # type: ignore
        """Build TopIndustries protobuf message from dictionary."""
        top_ind = hr_analytics_pb2.TopIndustries()

        if not industries_data:
            return top_ind

        top_ind.metric_name = HRAnalyticsProtobufService._ensure_string(industries_data.get('metric_name'))
        top_ind.period_start = HRAnalyticsProtobufService._ensure_string(industries_data.get('period_start'))
        top_ind.period_end = HRAnalyticsProtobufService._ensure_string(industries_data.get('period_end'))
        top_ind.period_days = HRAnalyticsProtobufService._ensure_int(industries_data.get('period_days'))
        top_ind.total_applications = HRAnalyticsProtobufService._ensure_int(industries_data.get('total_applications'))

        for industry in industries_data.get('industries', []):
            ind = top_ind.industries.add()
            ind.industry_id = HRAnalyticsProtobufService._ensure_string(industry.get('industry_id'))
            ind.industry_name = HRAnalyticsProtobufService._ensure_string(industry.get('industry_name'))
            ind.applications_count = HRAnalyticsProtobufService._ensure_int(industry.get('applications_count'))
            ind.percentage = HRAnalyticsProtobufService._ensure_float(industry.get('percentage'))

        return top_ind

    @staticmethod
    def _build_hiring_dynamics(dynamics_data: Dict[str, Any]) -> 'hr_analytics_pb2.HiringDynamics':  # type: ignore
        """Build HiringDynamics protobuf message from dictionary."""
        dynamics = hr_analytics_pb2.HiringDynamics()

        if not dynamics_data:
            return dynamics

        dynamics.metric_name = HRAnalyticsProtobufService._ensure_string(dynamics_data.get('metric_name'))
        dynamics.current_period_start = HRAnalyticsProtobufService._ensure_string(
            dynamics_data.get('current_period_start'))
        dynamics.current_period_end = HRAnalyticsProtobufService._ensure_string(dynamics_data.get('current_period_end'))
        dynamics.previous_period_start = HRAnalyticsProtobufService._ensure_string(
            dynamics_data.get('previous_period_start'))
        dynamics.previous_period_end = HRAnalyticsProtobufService._ensure_string(
            dynamics_data.get('previous_period_end'))

        # Current period data points - handle both dict and already-serialized string
        current_period_data = dynamics_data.get('current_period', [])
        if isinstance(current_period_data, str):
            # Data was serialized - try to parse it
            try:
                current_period_data = json.loads(current_period_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse current_period data: {current_period_data}")
                current_period_data = []

        for point in current_period_data:
            if isinstance(point, str):
                # Skip string items - they shouldn't be here
                logger.warning(f"Skipping string item in current_period: {point}")
                continue
            dp = dynamics.current_period.add()
            dp.date = HRAnalyticsProtobufService._ensure_string(point.get('date') if isinstance(point, dict) else '')
            dp.hires = HRAnalyticsProtobufService._ensure_int(point.get('hires') if isinstance(point, dict) else 0)
            dp.interval = HRAnalyticsProtobufService._ensure_string(
                point.get('interval') if isinstance(point, dict) else 'day')

        # Previous period data points - handle both dict and already-serialized string
        previous_period_data = dynamics_data.get('previous_period', [])
        if isinstance(previous_period_data, str):
            # Data was serialized - try to parse it
            try:
                previous_period_data = json.loads(previous_period_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse previous_period data: {previous_period_data}")
                previous_period_data = []

        for point in previous_period_data:
            if isinstance(point, str):
                # Skip string items - they shouldn't be here
                logger.warning(f"Skipping string item in previous_period: {point}")
                continue
            dp = dynamics.previous_period.add()
            dp.date = HRAnalyticsProtobufService._ensure_string(point.get('date') if isinstance(point, dict) else '')
            dp.hires = HRAnalyticsProtobufService._ensure_int(point.get('hires') if isinstance(point, dict) else 0)
            dp.interval = HRAnalyticsProtobufService._ensure_string(
                point.get('interval') if isinstance(point, dict) else 'day')

        return dynamics

    @staticmethod
    def _build_yearly_data(yearly_data: Dict[str, Any]) -> 'hr_analytics_pb2.YearlyData':  # type: ignore
        """Build YearlyData protobuf message from dictionary."""
        data = hr_analytics_pb2.YearlyData()

        if not yearly_data:
            return data

        data.year = HRAnalyticsProtobufService._ensure_int(yearly_data.get('year'))
        data.start_date = HRAnalyticsProtobufService._ensure_string(yearly_data.get('start_date'))
        data.end_date = HRAnalyticsProtobufService._ensure_string(yearly_data.get('end_date'))
        data.total_applications = HRAnalyticsProtobufService._ensure_int(yearly_data.get('total_applications'))

        for monthly in yearly_data.get('monthly_data', []):
            md = data.monthly_data.add()
            md.month = HRAnalyticsProtobufService._ensure_int(monthly.get('month'))
            md.month_name = HRAnalyticsProtobufService._ensure_string(monthly.get('month_name'))
            md.year = HRAnalyticsProtobufService._ensure_int(monthly.get('year'))
            md.date = HRAnalyticsProtobufService._ensure_string(monthly.get('date'))
            md.applications_count = HRAnalyticsProtobufService._ensure_int(monthly.get('applications_count'))

        return data

    @staticmethod
    def _build_app_response_dynamics(
            dynamics_data: Dict[str, Any]) -> 'hr_analytics_pb2.ApplicationResponseDynamicsYearly':  # type: ignore
        """Build ApplicationResponseDynamicsYearly protobuf message from dictionary."""
        dynamics = hr_analytics_pb2.ApplicationResponseDynamicsYearly()

        if not dynamics_data:
            return dynamics

        dynamics.metric_name = HRAnalyticsProtobufService._ensure_string(dynamics_data.get('metric_name'))

        # Current year data
        current_year = dynamics_data.get('current_year', {})
        if current_year:
            dynamics.current_year.CopyFrom(
                HRAnalyticsProtobufService._build_yearly_data(current_year)
            )

        # Previous year data
        previous_year = dynamics_data.get('previous_year', {})
        if previous_year:
            dynamics.previous_year.CopyFrom(
                HRAnalyticsProtobufService._build_yearly_data(previous_year)
            )

        return dynamics

    @staticmethod
    def _build_analytics(analytics_data: Dict[str, Any]) -> 'hr_analytics_pb2.Analytics':  # type: ignore
        """Build Analytics protobuf message from dictionary."""
        analytics = hr_analytics_pb2.Analytics()

        # Top Industries
        top_ind = analytics_data.get('top_industries')
        if top_ind:
            analytics.top_industries.CopyFrom(
                HRAnalyticsProtobufService._build_top_industries(top_ind)
            )

        # Hiring Dynamics
        hiring_dyn = analytics_data.get('hiring_dynamics')
        if hiring_dyn:
            analytics.hiring_dynamics.CopyFrom(
                HRAnalyticsProtobufService._build_hiring_dynamics(hiring_dyn)
            )

        # Application Response Dynamics Yearly
        app_resp = analytics_data.get('application_response_dynamics_yearly')
        if app_resp:
            analytics.application_response_dynamics_yearly.CopyFrom(
                HRAnalyticsProtobufService._build_app_response_dynamics(app_resp)
            )

        return analytics

    @staticmethod
    def encode_analytics_data(analytics_data: Dict[str, Any]) -> bytes:
        """
        Encode HR analytics data dictionary to PURE protobuf binary format.
        
        NO JSON inside - everything is proper protobuf.
        
        Args:
            analytics_data: Dictionary containing HR analytics data
            
        Returns:
            bytes: Pure protobuf binary encoded data with WorkXplorer header
            
        Raises:
            Exception: If encoding fails
        """
        if hr_analytics_pb2 is None:
            raise RuntimeError(
                "Protobuf module not compiled. Run: "
                "cd apps/general/services/analytics && "
                "python -m grpc_tools.protoc -I. --python_out=. hr_analytics.proto"
            )

        try:
            # Create the main protobuf message
            message = hr_analytics_pb2.HRAnalyticsData()

            # Set string fields with type safety
            message.source = HRAnalyticsProtobufService._ensure_string(
                analytics_data.get('source')
            )
            message.timestamp = HRAnalyticsProtobufService._ensure_string(
                analytics_data.get('timestamp')
            )
            message.analytics_timestamp = HRAnalyticsProtobufService._ensure_string(
                analytics_data.get('analytics_timestamp')
            )

            # Build nested messages - all pure protobuf
            message.meta.CopyFrom(
                HRAnalyticsProtobufService._build_meta(
                    analytics_data.get('meta', {})
                )
            )

            message.company.CopyFrom(
                HRAnalyticsProtobufService._build_company(
                    analytics_data.get('company', {})
                )
            )

            message.cards.CopyFrom(
                HRAnalyticsProtobufService._build_cards(
                    analytics_data.get('cards', {})
                )
            )

            message.analytics.CopyFrom(
                HRAnalyticsProtobufService._build_analytics(
                    analytics_data.get('analytics', {})
                )
            )

            # Serialize to pure protobuf binary
            protobuf_binary = message.SerializeToString()

            # Add WorkXplorer header for identification
            header = WORKXPLORER_HEADER
            version = bytes([HR_PROTOBUF_VERSION])
            length = len(protobuf_binary).to_bytes(4, byteorder='little')

            final_binary = header + version + length + protobuf_binary

            # Log compression stats
            json_size = len(json.dumps(analytics_data, ensure_ascii=False, default=str).encode('utf-8'))
            protobuf_size = len(final_binary)
            compression_ratio = (1 - protobuf_size / json_size) * 100 if json_size > 0 else 0

            logger.debug(
                f"PURE protobuf encoding: JSON {json_size} bytes -> Protobuf {protobuf_size} bytes "
                f"(compression: {compression_ratio:.1f}%)"
            )

            return final_binary

        except Exception as e:
            logger.error(f"Failed to encode HR analytics data to protobuf: {e}")
            raise

    @staticmethod
    def decode_analytics_data(binary_data: bytes) -> Dict[str, Any]:
        """
        Decode protobuf binary data back to analytics dictionary.
        
        Args:
            binary_data: Pure protobuf binary encoded data with WorkXplorer header
            
        Returns:
            Dict[str, Any]: Decoded HR analytics data
            
        Raises:
            ValueError: If data format is invalid
            Exception: If decoding fails
        """
        if hr_analytics_pb2 is None:
            raise RuntimeError("Protobuf module not compiled")

        try:
            if len(binary_data) < 9:
                raise ValueError("Invalid protobuf data: too short")

            # Verify header
            if binary_data[:4] != WORKXPLORER_HEADER:
                raise ValueError("Invalid protobuf data: bad header")

            # Check version
            version = binary_data[4]
            if version != HR_PROTOBUF_VERSION:
                raise ValueError(f"Unsupported protobuf version: {version}, expected: {HR_PROTOBUF_VERSION}")

            # Get length
            length = int.from_bytes(binary_data[5:9], byteorder='little')

            # Extract and parse protobuf data
            protobuf_data = binary_data[9:9 + length]

            message = hr_analytics_pb2.HRAnalyticsData()
            message.ParseFromString(protobuf_data)

            # Convert back to dictionary
            return HRAnalyticsProtobufService._message_to_dict(message)

        except Exception as e:
            logger.error(f"Failed to decode protobuf data: {e}")
            raise

    @staticmethod
    def _message_to_dict(message: 'hr_analytics_pb2.HRAnalyticsData') -> Dict[str, Any]:  # type: ignore
        """Convert protobuf message back to dictionary."""
        return {
            'source': message.source,
            'timestamp': message.timestamp,
            'analytics_timestamp': message.analytics_timestamp,
            'meta': {
                'env': message.meta.env,
                'company_id': message.meta.company_id,
            },
            'company': HRAnalyticsProtobufService._company_to_dict(message.company),
            'cards': {
                'average_view_time': {
                    'value': message.cards.average_view_time.value,
                    'unit': message.cards.average_view_time.unit,
                    'label': message.cards.average_view_time.label,
                    'total_views': message.cards.average_view_time.total_views,
                },
                'open_vacancies': {
                    'value': message.cards.open_vacancies.value,
                    'label': message.cards.open_vacancies.label,
                    'percentage_change': (
                        message.cards.open_vacancies.percentage_change
                        if message.cards.open_vacancies.HasField('percentage_change')
                        else None
                    ),
                },
                'applications_count': {
                    'value': message.cards.applications_count.value,
                    'label': message.cards.applications_count.label,
                    'percentage_change': (
                        message.cards.applications_count.percentage_change
                        if message.cards.applications_count.HasField('percentage_change')
                        else None
                    ),
                },
                'vacancy_views': {
                    'value': message.cards.vacancy_views.value,
                    'label': message.cards.vacancy_views.label,
                    'percentage_change': (
                        message.cards.vacancy_views.percentage_change
                        if message.cards.vacancy_views.HasField('percentage_change')
                        else None
                    ),
                    'unique_viewers': message.cards.vacancy_views.unique_viewers,
                },
                'average_candidate_age': {
                    'value': (
                        message.cards.average_candidate_age.value
                        if message.cards.average_candidate_age.HasField('value')
                        else None
                    ),
                    'unit': message.cards.average_candidate_age.unit,
                    'label': message.cards.average_candidate_age.label,
                    'age_change': (
                        message.cards.average_candidate_age.age_change
                        if message.cards.average_candidate_age.HasField('age_change')
                        else None
                    ),
                },
            },
            'analytics': {
                'top_industries': HRAnalyticsProtobufService._top_industries_to_dict(
                    message.analytics.top_industries
                ),
                'hiring_dynamics': HRAnalyticsProtobufService._hiring_dynamics_to_dict(
                    message.analytics.hiring_dynamics
                ),
                'application_response_dynamics_yearly': HRAnalyticsProtobufService._app_response_to_dict(
                    message.analytics.application_response_dynamics_yearly
                ),
            },
        }

    @staticmethod
    def _top_industries_to_dict(top_ind: 'hr_analytics_pb2.TopIndustries') -> Dict[str, Any]:  # type: ignore
        """Convert TopIndustries message to dict."""
        if not top_ind.metric_name:
            return None

        return {
            'metric_name': top_ind.metric_name,
            'period_start': top_ind.period_start,
            'period_end': top_ind.period_end,
            'period_days': top_ind.period_days,
            'total_applications': top_ind.total_applications,
            'industries': [
                {
                    'industry_id': ind.industry_id,
                    'industry_name': ind.industry_name,
                    'applications_count': ind.applications_count,
                    'percentage': ind.percentage,
                }
                for ind in top_ind.industries
            ],
        }

    @staticmethod
    def _company_to_dict(company: 'hr_analytics_pb2.Company') -> Dict[str, Any]:  # type: ignore
        """Convert Company message to dict.
        
        Note: Vacancy data is no longer included in company analytics.
        It is sent via a separate dedicated webhook.
        """
        return {
            'id': company.id,
            'name': company.name,
            'domain': company.domain or None,
            'tin': company.tin,
            'is_active': company.is_active,
            'description': company.description or None,
            'address': company.address or None,
            'website': company.website or None,
            'photo': company.photo or None,
        }

    @staticmethod
    def _vacancy_analytics_to_dict(vacancy: 'hr_analytics_pb2.VacancyAnalytics') -> Dict[str, Any]:  # type: ignore
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
            'cards': HRAnalyticsProtobufService._vacancy_cards_to_dict(vacancy.cards),
        }

    @staticmethod
    def _vacancy_cards_to_dict(cards: 'hr_analytics_pb2.VacancyCards') -> Dict[str, Any]:  # type: ignore
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
    def _hiring_dynamics_to_dict(dynamics: 'hr_analytics_pb2.HiringDynamics') -> Dict[str, Any]:  # type: ignore
        """Convert HiringDynamics message to dict."""
        if not dynamics.metric_name:
            return None

        return {
            'metric_name': dynamics.metric_name,
            'current_period_start': dynamics.current_period_start,
            'current_period_end': dynamics.current_period_end,
            'previous_period_start': dynamics.previous_period_start,
            'previous_period_end': dynamics.previous_period_end,
            'current_period': [
                {'date': dp.date, 'hires': dp.hires, 'interval': dp.interval}
                for dp in dynamics.current_period
            ],
            'previous_period': [
                {'date': dp.date, 'hires': dp.hires, 'interval': dp.interval}
                for dp in dynamics.previous_period
            ],
        }

    @staticmethod
    def _yearly_data_to_dict(yearly: 'hr_analytics_pb2.YearlyData') -> Dict[str, Any]:  # type: ignore
        """Convert YearlyData message to dict."""
        return {
            'year': yearly.year,
            'start_date': yearly.start_date,
            'end_date': yearly.end_date,
            'total_applications': yearly.total_applications,
            'monthly_data': [
                {
                    'month': md.month,
                    'month_name': md.month_name,
                    'year': md.year,
                    'date': md.date,
                    'applications_count': md.applications_count,
                }
                for md in yearly.monthly_data
            ],
        }

    @staticmethod
    def _app_response_to_dict(dynamics: 'hr_analytics_pb2.ApplicationResponseDynamicsYearly') -> Dict[
        str, Any]:  # type: ignore
        """Convert ApplicationResponseDynamicsYearly message to dict."""
        if not dynamics.metric_name:
            return None

        return {
            'metric_name': dynamics.metric_name,
            'current_year': HRAnalyticsProtobufService._yearly_data_to_dict(dynamics.current_year),
            'previous_year': HRAnalyticsProtobufService._yearly_data_to_dict(dynamics.previous_year),
        }

    @staticmethod
    def validate_analytics_data(analytics_data: Dict[str, Any]) -> bool:
        """
        Validate HR analytics data structure before encoding.
        
        Args:
            analytics_data: Dictionary containing HR analytics data
            
        Returns:
            bool: True if valid, False otherwise
        """
        try:
            required_fields = [
                'source', 'timestamp', 'meta', 'company', 'cards', 'analytics'
            ]

            for field in required_fields:
                if field not in analytics_data:
                    logger.warning(f"Missing required field: {field}")
                    return False

            # Validate company data
            company = analytics_data.get('company', {})
            if not company.get('id'):
                logger.warning("Missing company.id")
                return False

            # Validate cards structure
            cards = analytics_data.get('cards', {})
            required_cards = [
                'average_view_time', 'open_vacancies', 'applications_count',
                'vacancy_views', 'average_candidate_age'
            ]
            for card in required_cards:
                if card not in cards:
                    logger.warning(f"Missing card: {card}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating HR analytics data: {e}")
            return False

    @staticmethod
    def get_encoding_info(analytics_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get information about protobuf encoding efficiency.
        
        Args:
            analytics_data: Dictionary containing HR analytics data
            
        Returns:
            Dict with encoding statistics or error information
        """
        try:
            json_str = json.dumps(analytics_data, ensure_ascii=False, default=str)
            json_size = len(json_str.encode('utf-8'))

            protobuf_data = HRAnalyticsProtobufService.encode_analytics_data(analytics_data)
            protobuf_size = len(protobuf_data)

            compression_ratio = (1 - protobuf_size / json_size) * 100 if json_size > 0 else 0

            return {
                'json_size_bytes': json_size,
                'protobuf_size_bytes': protobuf_size,
                'compression_ratio_percent': round(compression_ratio, 1),
                'size_reduction_bytes': json_size - protobuf_size,
                'format': 'Pure Protobuf Binary v3',
                'is_compiled': hr_analytics_pb2 is not None,
            }
        except Exception as e:
            return {
                'error': str(e),
                'is_compiled': hr_analytics_pb2 is not None,
            }
