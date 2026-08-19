# HR Analytics Module

This module handles HR analytics data collection and transmission to the external HR Analytics service.

## Structure

```
services/analytics/
├── __init__.py              # Module exports
├── main.py                  # HRAnalyticsService - main orchestrator
├── cards.py                 # 5 dashboard card metrics
├── vacancy_analytics.py     # Per-vacancy analytics metrics
├── top_industries.py        # Top industries calculation
├── hiring_dynamics.py       # Hiring dynamics chart data
├── application_dynamics.py  # Application dynamics yearly
├── protobuf_service.py      # Protobuf encoding/decoding
├── data_processing.py       # Data preparation utilities
├── utils.py                 # Shared utilities
├── hr_analytics.proto       # Protobuf schema definition
└── hr_analytics_pb2.py      # Compiled protobuf (auto-generated)
```

## Metrics

### Dashboard Cards (5 metrics - Company Level)

1. **Average View Time** - Average time candidates spend viewing job pages
2. **Open Vacancies** - Number of open jobs at end of period
3. **Applications Count** - Number of applications received
4. **Vacancy Views** - Number of job page views
5. **Average Candidate Age** - Average age of applying candidates

### Per-Vacancy Analytics (5 metrics)

Each vacancy that had changes today includes its own metrics:

1. **Time to Hire** - Raw data for calculating average time from application to hire
    - `hired_count`: Number of hired candidates
    - `total_days_to_hire`: Sum of all days to hire
    - `hire_records`: Individual hire records with timing details

2. **Overall Conversion** - Raw numbers for conversion calculation
    - `total_applications`: All candidates who applied
    - `total_hired`: Candidates who reached "Offer Accepted" status

3. **Number of Views** - View count for the vacancy
    - `total_views`: All view events
    - `unique_viewers`: Distinct candidates who viewed

4. **Number of Applications** - Application count
    - `count`: Total applications received

5. **Average Age of Applicants** - Raw data for age calculation
    - `applicants_with_age`: Candidates with known birth dates
    - `total_age_sum`: Sum of all ages

### Charts

1. **Top Industries** - Which industries receive the most applications
2. **Hiring Dynamics** - New hires over time (daily/weekly/monthly)
3. **Application Dynamics Yearly** - Monthly application distribution with YoY comparison

## Usage

### Using HRAnalyticsService

```python
from apps.general.services.analytics import HRAnalyticsService

# Get complete analytics for a company (includes vacancy analytics)
analytics = HRAnalyticsService.get_company_analytics(
    company_id="uuid-string",
    end_date=timezone.now(),
    period_days=30
)

# Get quick summary
summary = HRAnalyticsService.get_analytics_summary(company_id)
```

### Using Individual Metrics

```python
from apps.general.services.analytics import (
    calculate_average_view_time,
    calculate_applications_count,
    calculate_top_industries,
)

# Calculate specific metrics
view_time = calculate_average_view_time(start_date, end_date, vacancy_ids)
apps = calculate_applications_count(start_date, end_date, period_days, company_id)
industries = calculate_top_industries(start_date, end_date, period_days, company_id)
```

### Using Vacancy Analytics

```python
from apps.general.services.analytics import (
    get_company_vacancies_analytics,
    get_vacancies_changed_today,
    calculate_vacancy_time_to_hire,
    calculate_vacancy_conversion,
)

# Get all vacancies changed today with their analytics
vacancies_analytics = get_company_vacancies_analytics(company_id="uuid-string")

# Get list of vacancies changed today
vacancies = get_vacancies_changed_today(company_id="uuid-string")

# Calculate specific vacancy metrics
tth = calculate_vacancy_time_to_hire(vacancy_id="uuid-string")
conversion = calculate_vacancy_conversion(vacancy_id="uuid-string")
```

## Vacancy Analytics Logic

### Changed Today Detection

A vacancy is considered "changed today" if any of the following occurred:

- The vacancy was created today (`created_at`)
- The vacancy was updated today (`updated_at`)
- Any application for the vacancy changed today (`applied_at`, `updated_at`, `hired_at`)
- Any view for the vacancy was recorded today (`session_start`)

This ensures we capture all vacancies with relevant activity, not just those with direct field changes.

### Raw Data Approach

We send **raw numbers** to the HR Analytics service, which handles:

- Calculating averages (e.g., average time to hire)
- Computing percentages (e.g., conversion rate)
- Comparing with previous periods

This approach:

- Keeps the WorkXplorer side simple
- Allows the analytics service to apply custom calculation logic
- Enables period comparisons on the analytics side

## RQ Tasks

Located in `apps/general/tasks.py`:

```python
from apps.general.tasks import send_hr_analytics_data, send_single_company_analytics

# Send analytics for all companies (enqueues individual jobs)
send_hr_analytics_data()

# Send analytics for a single company
send_single_company_analytics(company_id="uuid-string")
```

## Data Flow

1. **Scheduler** triggers `send_hr_analytics_data()` periodically
2. For each active company, `send_single_company_analytics()` is enqueued
3. `HRAnalyticsService.get_company_analytics()` collects all metrics:
    - Company info + vacancies changed today with their metrics
    - Dashboard cards
    - Chart analytics
4. Data is encoded using protobuf (`HRAnalyticsProtobufService`)
5. Binary data is sent to external HR Analytics service

## Protobuf Schema

Located in `services/analytics/hr_analytics.proto`

Key messages:

- `HRAnalyticsData` - Main container
- `Company` - Company info + `repeated VacancyAnalytics vacancies`
- `VacancyAnalytics` - Vacancy info + `VacancyCards cards`
- `VacancyCards` - 5 vacancy metrics (TimeToHire, Conversion, Views, Applications, AverageAge)
- `Cards` - 5 company-level dashboard metrics
- `Analytics` - Chart data (TopIndustries, HiringDynamics, ApplicationResponseDynamicsYearly)

### Compiling Protobuf

```bash
cd apps/general/services/analytics
python -m grpc_tools.protoc -I. --python_out=. hr_analytics.proto
```

## Configuration

Environment variables:

- `HR_ANALYTICS_WEBHOOK_URL` - External service endpoint
- `REDIS_URL` - Redis connection for RQ

## Comparison with EduPartner

This module follows the same pattern as EduPartner analytics:

| Component        | EduPartner                   | HR Analytics            |
|------------------|------------------------------|-------------------------|
| Service          | `EduPartnerAnalyticsService` | `HRAnalyticsService`    |
| Tasks            | `apps/edupartners/tasks.py`  | `apps/general/tasks.py` |
| Analytics folder | `services/analytics/`        | `services/analytics/`   |
| Protobuf         | `analytics.proto`            | `hr_analytics.proto`    |
