You're absolutely right. I apologize for not following your structure closely. Let me rewrite it according to your exact
template:

# General App Documentation

## 1. Header & Overview

**General App** - Core utilities and shared functionality for WorkXplorer

This app provides email template management, avatar handling, and company verification workflows. It centralizes common
features used across the entire application.

## 2. Features

- Multi-language email templates with dynamic content rendering
- Avatar management system with file validation
- Company verification workflow with automated notifications
- Asynchronous email queue using Redis Queue (RQ)
- Batch email processing to prevent N+1 queries
- Job status tracking for monitoring queued tasks
- Admin interface for templates and avatars

## 3. API Endpoints

### Public Endpoints

#### List Profile Avatars

```
GET /api/general/avatars/
```

**Authentication**: None

**Response**:

```json
{
  "count": 2,
  "results": [
    {
      "id": 1,
      "image": "https://example.com/media/profile/avatars/avatar1.png",
      "is_active": true,
      "created_at": "2025-10-11T08:00:00Z"
    }
  ]
}
```

**Features**:

- Returns only active avatars
- Paginated response
- No authentication required

---

#### List Inactive Companies

```
GET /api/general/inactive-companies/
```

**Authentication**: None

**Response**:

```json
{
  "count": 1,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Tech Corp",
      "tin": "123456789",
      "is_active": false
    }
  ]
}
```

**Features**:

- Filters companies where is_active=False
- Paginated response

---

#### Confirm/Reject Companies

```
POST /api/general/confirm-company/
```

**Authentication**: None (should be restricted in production)

**Request**:

```json
{
  "company_ids": ["550e8400-e29b-41d4-a716-446655440000"],
  "is_active": true
}
```

**Response**:

```json
{
  "sent_emails": ["admin@techcorp.com"],
  "failed_emails": [],
  "not_found_company_ids": [],
  "recruiters_missing_email": []
}
```

**Features**:

- Validates company_ids as list
- Updates company.is_active when confirming
- Sends different templates based on admin status
- Prevents duplicate emails per address
- Batch generates password reset URLs

## 4. Models

### EmailTemplate

Multi-language email template with file-based HTML bodies.

**Fields**:

- `template_type`: Template purpose identifier (e.g., "reset-password")
- `name`: Human-readable template name
- `language`: Language code (uz/ru/en)
- `subject`: Email subject with Django template support
- `body`: HTML file uploaded to "email_templates/"

**Features**:

- Unique constraint on (name, language)
- Django template syntax in subject and body
- Automatic .html file validation
- Language fallback mechanism

**Use Cases**:

- Password reset emails
- Company confirmation/rejection notifications
- Welcome emails for recruiters

---

### Avatar

Profile picture management.

**Fields**:

- `image`: Uploaded to "profile/avatars/" (jpg/jpeg/png/svg)
- `is_active`: Visibility toggle
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

**Features**:

- Extends AbstractBaseModel
- File extension validation
- Soft-delete via is_active flag

**Use Cases**:

- Default profile pictures
- System-provided avatar options

## 5. Business Logic

### Email Queue Architecture

**Two-Layer Service**:

- BaseEmailService: Reusable methods for Redis Queue, template rendering, job enqueueing
- EmailService: Specific workflows that enqueue worker functions

**Template Rendering**:

```python
# Fetch template, render with Django Template engine
template = EmailTemplate.objects.filter(
    template_type="reset-password", language="uz"
).first()
ctx = Context({"user_full_name": "John", "reset_url": "..."})
subject = Template(template.subject).render(ctx)
body = Template(template.body.read()).render(ctx)
```

**Queue Workflow**:

- Job enqueued immediately in web process
- RQ worker picks up job in separate process
- Worker renders template and sends email
- Job status updated in Redis

### Company Confirmation Batch Processing

**Prevent N+1 Queries**:

```python
# Single query with prefetch_related
companies = Company.objects.filter(id__in=ids).prefetch_related(
    Prefetch('recruiters', queryset=Recruiter.objects.prefetch_related(...))
)
# Batch generate all URLs at once
url_map = _build_set_password_url_batch(all_emails, request)
```

**Email Deduplication**:

- Admin emails take precedence over recruiter emails
- Two dictionaries track admin vs recruiter contexts
- Single email sent per unique address

**Template Selection**:

- Admins: "confirm-company" or "rejected-company"
- Recruiters: "set-password"

## 6. Multi-Language Support

**Supported Languages**: uz (Uzbek), ru (Russian), en (English)

**Selection Priority**:

- Accept-Language header from request
- Exact template match for language
- Fallback to first available template
- Default to "uz" if invalid

**Common Template Variables**:

- `{{ user_full_name }}`, `{{ user_email }}`, `{{ reset_url }}`, `{{ site_name }}`, `{{ companies }}`

## 7. Error Responses

### 400 Bad Request

```json
{ "error": "company_ids must be a list of company id strings." }
```

```json
{ "error": "is_active field is required and must be boolean." }
```

### 405 Method Not Allowed

```json
{ "detail": "Method \"GET\" not allowed." }
```

### Partial Success

```json
{
  "sent_emails": ["admin@company.com"],
  "failed_emails": ["invalid@email.com"],
  "not_found_company_ids": ["550e8400-..."],
  "recruiters_missing_email": [
    { "company_id": "...", "company_name": "Tech Corp", "recruiter_id": 123 }
  ]
}
```

## 8. Security

**Current State**:

- Most endpoints use AllowAny (for development)
- No authentication on company confirmation

**Production Recommendations**:

- CompanyConfirmAPIView should require admin auth
- InActiveCompanyAPIView should require admin auth
- Implement rate limiting at application level

**Validation**:

- File extension validation on uploads
- Email address validation through Django
- Company ID deduplication
- Boolean type validation with multiple formats

## 9. Testing

### Run Tests

```bash
python manage.py test apps.general
python manage.py test apps.general.tests.test_models
coverage run --source='apps.general' manage.py test apps.general
```

### Coverage

- EmailTemplate CRUD and unique constraints
- Avatar creation and status toggling
- API endpoint responses and validation
- Empty/invalid input handling
- HTTP method restrictions

## 10. Admin Interface

### EmailTemplate Admin

- List display: ID, name, template_type, language, subject
- Search: name, subject, template_type
- Filters: language, template_type
- Read-only: ID field
- File upload for HTML body

### Avatar Admin

- Basic registration with standard CRUD
- Image field with validation
- Active/inactive toggle

## 11. Performance

### Optimizations

- prefetch_related eliminates N+1 queries
- Asynchronous email via Redis Queue
- Batch URL generation for multiple users
- Set-based email deduplication

### Recommendations

- Cache frequently used templates
- Add RQ dashboard for monitoring
- Multiple workers for high-volume periods
- Redis sentinel for high availability

## 12. Integration Points

### Used By Other Apps

- Authentication app: password reset and company confirmation emails
- Profiles app: accesses RecruiterProfile for admin checking

### Provides Services

- Email template rendering to all apps
- Asynchronous email queue infrastructure
- Avatar management for profiles

### Dependencies

- Redis for RQ queue
- SMTP server via Django settings
- File storage for templates and avatars
