# Applications App

The Applications app handles the job application process, allowing candidates to apply to vacancies and recruiters to manage those applications through the hiring pipeline.

## Overview

This app serves as the bridge between candidates and job opportunities, providing a complete application lifecycle management system with status tracking, document uploads, and role-based access control.

## Features

- **Application Submission**: Candidates can apply to job vacancies with resumes and additional documents
- **Status Tracking**: Applications progress through various stages (Applied → Under Review → Interview → etc.)
- **Document Management**: Support for multiple document types (certificates, portfolios, references)
- **Role-based Access**: Separate views and permissions for candidates and recruiters
- **Audit Trail**: Track who made changes and when
- **Daily Telegram Report**: Scheduled digest of application activity per company

## Daily Telegram Report

A scheduled RQ job pushes a daily application digest to the WorkXplorer Telegram
bot, which renders and posts it to the group's reporting topic.

| Piece | Location |
|-------|----------|
| Statistics + delivery | `services/daily_report.py` |
| RQ task entry point | `tasks.send_daily_application_report_task` |
| Cron registration | `services/scheduler.py` (auto-runs from `ApplicationsConfig.ready()`) |
| Manual run / preview | `manage.py send_daily_application_report` |
| On-demand trigger | `POST /api/v1/applications/reports/daily/trigger/` |

### On-demand trigger

`views/reports.py` exposes a shared-secret endpoint used by the Telegram bot's
`/report` command. It authenticates on the `X-API-Secret` header rather than a
user session, because the caller is a service; the secret is the same
`TELEGRAM_BOT_API_SECRET` used for the outbound direction. The endpoint queues
the existing RQ task and returns `202` immediately, so the report is delivered
through the normal push path rather than inside the request.

An unset `TELEGRAM_BOT_API_SECRET` returns `503` rather than accepting an empty
header as valid.

The report covers the previous full day in `settings.TIME_ZONE` (Asia/Tashkent):
application counts for that day, its ISO week to date, and all time — each with
the equivalent earlier period for a trend — plus the most active companies, two
status breakdowns, and growth (new companies, new vacancies, open vacancies).

The status breakdowns show where that day's applications currently stand and
where the whole backlog stands. `JobApplication.status` holds a company-scoped
status *key* rather than a foreign key, so `_status_breakdown` loads the
`ApplicationStatusModel` key → `StatusCategory` map once and folds the grouped
counts onto it in Python — otherwise every company's custom status names would
appear as separate entries. Legacy `ApplicationStatus` values still on older
rows map onto the same categories via `LEGACY_STATUS_CATEGORIES`, and anything
unrecognised is bucketed as `OTHER` so counts always sum to the totals.

`_signup_breakdown` adds new candidate signups grouped by `Candidate.edupartner`,
using `date_joined` for the windows. Candidates without an educational partner
are returned as a separate `no_university` bucket rather than ranked among named
universities or silently dropped, so the per-university numbers reconcile with
the signup total.

Only raw numbers are sent; all message formatting lives in the bot repository,
so wording changes don't need a backend deploy.

### Settings

| Setting | Env var | Default | Purpose |
|---------|---------|---------|---------|
| `DAILY_APPLICATION_REPORT_CRON` | same | `0 4 * * *` (UTC = 09:00 Tashkent) | When the job runs |
| `DAILY_APPLICATION_REPORT_ENABLED` | same | `true` | Set to `false` to skip registering the job |
| `DAILY_APPLICATION_REPORT_TOP_COMPANIES` | same | `5` | Companies listed by name before the "and N more" line |
| `TELEGRAM_BOT_API_URL` | same | `http://workxplorer-bot:5000` | Bot API base URL |
| `TELEGRAM_BOT_API_SECRET` | same | — | Shared secret; delivery is skipped when unset |

```bash
# Preview the numbers without sending anything
python manage.py send_daily_application_report --dry-run

# Re-send a day the scheduled job missed
python manage.py send_daily_application_report --date 2026-07-27
```

## API Endpoints

### Candidate Endpoints

#### Apply to Vacancy

```http
POST /api/applications/apply/
```

**Purpose**: Submit a new job application

**Authentication**: Required (Candidate only)

**Request Body**:

```json
{
  "vacancy_id": "uuid",
  "resume_id": "uuid", // optional, uses latest if not provided
  "cover_letter": "string", // optional
  "portfolio_url": "string", // optional
  "earliest_start_date": "YYYY-MM-DD", // optional
  "documents_data": [
    // optional
    {
      "document_type": "CERTIFICATE",
      "title": "AWS Certification"
    }
  ]
}
```

**Response** (201 Created):

```json
{
  "message": "Application submitted successfully",
  "application": {
    "id": "uuid",
    "vacancy_title": "Software Engineer",
    "company_name": "Tech Corp",
    "status": "APPLIED",
    "applied_at": "2023-08-19T10:30:00Z"
    // ... full application details
  }
}
```

**Business Logic**:

- Automatically sets candidate from authenticated user
- Prevents duplicate applications to same vacancy
- Uses candidate's latest resume if none specified
- Validates vacancy exists and is active

---

#### Get My Applications

```http
GET /api/applications/my-applications/
```

**Purpose**: List all applications submitted by the current candidate

**Authentication**: Required (Candidate only)

**Response** (200 OK):

```json
[
  {
    "id": "uuid",
    "vacancy_title": "Software Engineer",
    "company_name": "Tech Corp",
    "status": "OFFER_ACCEPTED",
    "status_display": "Offer accepted",
    "applied_at": "2023-08-19T10:30:00Z",
    "updated_at": "2023-08-20T14:15:00Z",
    "days_since_application": 5,
    "can_withdraw": true
  }
]
```

---

#### Withdraw Application

```http
PUT /api/applications/{application_id}/withdraw/
```

**Purpose**: Withdraw a submitted application

**Authentication**: Required (Candidate only)

**Constraints**:

- Only own applications
- Can only withdraw from APPLIED, INTERVIEW_SCHEDULED, INTERVIEWED, or OFFERED status

**Response** (200 OK):

```json
{
  "message": "Application withdrawn successfully",
  "application": {
    // updated application data with WITHDRAWN status
  }
}
```

---

#### Accept Job Offer

```http
PUT /api/applications/{application_id}/accept-offer/
```

**Purpose**: Accept a job offer

**Authentication**: Required (Candidate only)

**Constraints**:

- Only own applications
- Can only accept applications with OFFERED status

**Response** (200 OK):

```json
{
  "message": "Offer accepted successfully", 
  "application": {
    // updated application data with OFFER_ACCEPTED status
  }
}
```

---

#### Reject Job Offer

```http
PUT /api/applications/{application_id}/reject-offer/
```

**Purpose**: Reject a job offer

**Authentication**: Required (Candidate only)

**Constraints**:

- Only own applications
- Can only reject applications with OFFERED status

**Response** (200 OK):

```json
{
  "message": "Offer rejected successfully",
  "application": {
    // updated application data with OFFER_REJECTED status
  }
}
```

---

#### Reapply to Vacancy

```http
PUT /api/applications/{application_id}/reapply/
```

**Purpose**: Reapply to a previously applied vacancy

**Authentication**: Required (Candidate only)

**Constraints**:

- Only own applications
- Can only reapply if status is WITHDRAWN

**Response** (200 OK):

```json
{
  "message": "Reapplication successful",
  "application": {
    // updated application data with APPLIED status
  }
}
```

---

### Recruiter Endpoints

#### Get Vacancy Applications

```http
GET /api/applications/vacancy/{vacancy_id}/
```

**Purpose**: List all applications for a specific vacancy

**Authentication**: Required (Recruiter only)

**Authorization**: Must be recruiter from the company that owns the vacancy

**Response** (200 OK):

```json
[
  {
    "id": "uuid",
    "candidate_email": "john@example.com",
    "candidate_name": "John Doe",
    "status": "APPLIED",
    "applied_at": "2023-08-19T10:30:00Z",
    "cover_letter": "I am excited about...",
    "resume_title": "Senior Developer Resume",
    "documents": [
      {
        "id": "uuid",
        "document_type": "CERTIFICATE",
        "title": "AWS Certification",
        "file_size_display": "2.1 MB"
      }
    ]
  }
]
```

---

#### Update Application Status

```http
PUT /api/applications/update-status/{application_id}/
```

**Purpose**: Update application status and add recruiter notes

**Authentication**: Required (Recruiter only)

**Authorization**: Must be recruiter from the company that owns the vacancy

**Request Body**:

```json
{
  "status": "INTERVIEWED",
  "recruiter_notes": "Strong technical skills, good culture fit",
  "earliest_start_date": "2023-09-15" // optional update
}
```

**Response** (200 OK):

```json
{
  // Updated application data
}
```

**Business Logic**:

- Validates status transitions based on user type (candidate vs recruiter)
- Automatically tracks who made the change and when  
- Requires notes when rejecting applications
- Maintains audit trail in recruiter_notes field
- Enforces role-based transition rules (e.g., only candidates can accept/reject offers)

---

### Shared Endpoints

#### Get Application Details

```http
GET /api/applications/{application_id}/
```

**Purpose**: Get detailed information about a specific application

**Authentication**: Required

**Authorization**:

- Candidates can view their own applications
- Recruiters can view applications to their company's vacancies

**Response** (200 OK):

```json
{
  "id": "uuid",
  "applied_at": "2023-08-19T10:30:00Z",
  "updated_at": "2023-08-20T14:15:00Z",
  "vacancy_title": "Software Engineer",
  "company_name": "Tech Corp",
  "candidate_email": "john@example.com", // visible to recruiters only
  "candidate_name": "John Doe",
  "cover_letter": "I am excited about this opportunity...",
  "status": "OFFER_ACCEPTED",
  "status_display": "Offer accepted",
  "days_since_application": 5,
  "can_withdraw": true,
  "recruiter_notes": "...", // visible to recruiters only
  "documents": [
    {
      "id": "uuid",
      "document_type": "CERTIFICATE",
      "title": "AWS Certification",
      "file": "/media/application_documents/cert.pdf",
      "file_size_display": "2.1 MB",
      "uploaded_at": "2023-08-19T10:35:00Z"
    }
  ]
}
```

## Models

### JobApplication

Main model representing a candidate's application to a vacancy.

**Key Fields**:

- `candidate`: ForeignKey to Candidate (who applied)
- `vacancy`: ForeignKey to Vacancy (what they applied for)
- `status`: Current stage in hiring process
- `applied_at`: When application was submitted
- `cover_letter`: Optional cover letter text
- `recruiter_notes`: Internal notes (not visible to candidates)

**Business Rules**:

- One application per candidate per vacancy (unique constraint)
- Status transitions are validated
- Automatic timestamp updates on status changes

### ApplicationDocument

Stores additional documents uploaded with applications.

**Key Fields**:

- `application`: ForeignKey to JobApplication
- `document_type`: Type of document (CERTIFICATE, PORTFOLIO, etc.)
- `title`: Human-readable document name
- `file`: Uploaded file
- `file_size`: Auto-calculated file size

### Application Status Flow

The status transition system enforces business rules based on user types:

#### Status Transition Rules

**From APPLIED status:**
- **Candidates can:** → WITHDRAWN
- **Recruiters can:** → REJECTED, INTERVIEW_SCHEDULED, OFFERED

**From WITHDRAWN status:**
- **Candidates can:** → APPLIED (reapply)
- **Recruiters can:** (no transitions allowed)

**From INTERVIEW_SCHEDULED status:**
- **Candidates can:** (no transitions allowed)
- **Recruiters can:** → REJECTED, INTERVIEWED, OFFERED

**From INTERVIEWED status:**
- **Candidates can:** (no transitions allowed)  
- **Recruiters can:** → REJECTED, OFFERED

**From OFFERED status:**
- **Candidates can:** → OFFER_ACCEPTED, OFFER_REJECTED
- **Recruiters can:** → REJECTED

**Terminal states** (no further transitions):
- REJECTED, OFFER_ACCEPTED, OFFER_REJECTED

#### Visual Status Flow

```
APPLIED ──┬─(candidate)──→ WITHDRAWN ──(candidate)──→ APPLIED
          │
          └─(recruiter)───→ INTERVIEW_SCHEDULED ──(recruiter)──→ INTERVIEWED
          │                      │                                   │
          │                      ├─(recruiter)──→ REJECTED           ├─(recruiter)──→ OFFERED
          │                      └─(recruiter)──→ OFFERED             └─(recruiter)──→ REJECTED
          │
          └─(recruiter)───→ REJECTED
          │
          └─(recruiter)───→ OFFERED ──┬─(candidate)──→ OFFER_ACCEPTED
                                      ├─(candidate)──→ OFFER_REJECTED  
                                      └─(recruiter)──→ REJECTED
```

## Frontend Integration Notes

### For Candidate Dashboard

1. **Application List**: Use `/my-applications/` to show application history with status badges
2. **Apply Form**: POST to `/apply/` with vacancy selection and optional fields
3. **Status Tracking**: Show visual progress indicator based on status
4. **Withdrawal**: Only show withdraw button when `can_withdraw` is true

### For Recruiter Dashboard

1. **Vacancy Management**: Use `/vacancy/{id}/` to see all applicants for a posting
2. **Application Review**: Use application detail endpoint with recruiter-specific fields
3. **Status Updates**: Provide dropdown for valid status transitions
4. **Bulk Actions**: Consider implementing bulk status updates for efficiency

### Document Handling

- Documents are uploaded separately from application metadata
- File size limits should be enforced on frontend
- Support common formats: PDF, DOC, DOCX, images
- Display file size in human-readable format

## Error Handling

### Common Error Responses

**403 Forbidden** - Wrong user type or permissions:

```json
{
  "error": "Only candidates can submit job applications"
}
```

**400 Bad Request** - Validation errors:

```json
{
  "error": {
    "detail": "You have already applied to this vacancy"
  }
}
```

**404 Not Found** - Resource doesn't exist or no access:

```json
{
  "error": "Application not found"
}
```

## Performance Considerations

- All list endpoints use `select_related()` for optimized queries
- Candidate queries are filtered by user to prevent data leaks
- File uploads are stored with organized directory structure
- Database indexes on frequently queried fields (candidate, vacancy, status)

## Security Features

- Role-based access control prevents cross-user data access
- Automatic user context injection prevents manual candidate/recruiter spoofing
- File upload validation and secure storage
- Audit trail for all status changes with timestamp and user tracking
