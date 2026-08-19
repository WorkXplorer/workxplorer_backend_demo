# Domain App

The Domain app manages professional domains (e.g., IT, Healthcare, Finance) and company-specific professions for job categorization and career guidance.

## Overview

This app provides a two-tier categorization system:

1. **Global Domains**: Admin-managed broad professional categories
2. **HR-Created Professions**: Company-specific job titles within domains

## Features

- **Domain Management**: Create and manage global professional domains
- **HR Profession Creation**: Company-specific profession definitions
- **Search & Autocomplete**: Fast domain search for dropdowns
- **Multi-Language Support**: Translations for uz/en/ru
- **Public Access**: Domains visible without authentication
- **Admin Controls**: Domain creation restricted to administrators

## API Endpoints

### Domain Endpoints

#### List and Create Domains

```http
GET /api/domains/
POST /api/domains/
```

**Authentication**:

- GET: None required
- POST: Admin only

**Query Parameters** (GET):

- `search`: Search by name or description

**GET Response**:

```json
{
  "count": 15,
  "results": [
    {
      "id": 1,
      "name": "Information Technology",
      "description": "IT and software development domain",
      "created_at": "2023-08-19T10:30:00Z",
      "updated_at": "2023-08-19T10:30:00Z"
    }
  ]
}
```

**POST Request**:

```json
{
  "name": "Finance",
  "description": "Financial services and banking"
}
```

---

#### Get Domain Details

```http
GET /api/domains/{id}/
```

**Authentication**: None required

**Response**:

```json
{
  "data": {
    "id": 1,
    "name": "Information Technology",
    "description": "IT and software development domain",
    "created_at": "2023-08-19T10:30:00Z",
    "updated_at": "2023-08-19T10:30:00Z"
  }
}
```

---

#### Domain Names (Autocomplete)

```http
GET /api/domains/list-names/
```

**Purpose**: Lightweight endpoint for dropdowns

**Query Parameters**:

- `search`: Filter by name prefix

**Response**:

```json
{
  "count": 3,
  "results": [
    { "id": 1, "name": "Information Technology" },
    { "id": 5, "name": "IT Services" }
  ]
}
```

**Features**:

- No pagination
- Only returns id and name
- Prioritizes exact matches
- Uses `istartswith` for fast prefix matching

---

### HR Profession Endpoints

#### List and Create Professions

```http
GET /api/domains/hr-professions/
POST /api/domains/hr-professions/
```

**Authentication**: Admin only

**Query Parameters** (GET):

- `company`: Filter by company UUID
- `created_by`: Filter by recruiter UUID
- `search`: Search name or description
- `ordering`: Sort by name, created_at

**GET Response**:

```json
{
  "count": 25,
  "results": [
    {
      "id": 1,
      "company_id": "company-uuid",
      "name": "Senior Backend Developer",
      "description": "Expert in Python and Django",
      "created_by_id": "recruiter-uuid",
      "created_at": "2023-08-19T10:30:00Z",
      "updated_at": "2023-08-19T10:30:00Z"
    }
  ]
}
```

**POST Request**:

```json
{
  "company": "company-uuid",
  "name": "Machine Learning Engineer",
  "description": "AI and ML model development",
  "created_by": "recruiter-uuid"
}
```

**Validation**:

- Name cannot be empty
- Description max 500 characters
- Company and recruiter must exist

---

#### Profession Details

```http
GET /api/domains/hr-professions/{profession_id}/
PUT /api/domains/hr-professions/{profession_id}/
PATCH /api/domains/hr-professions/{profession_id}/
DELETE /api/domains/hr-professions/{profession_id}/
```

**Authentication**: Required

---

## Models

### Domain

Global professional categories managed by admins.

**Fields**:

- `name`: Domain name (255 chars, unique)
- `description`: Optional description
- `created_at`, `updated_at`: Timestamps

**Features**:

- Unique names
- Alphabetically ordered
- Multi-language support (uz/en/ru)

**Use Cases**:

- Vacancy categorization
- Career quiz results
- Job board filtering

---

### HrCreatedProfession

Company-specific professions created by HR.

**Fields**:

- `company`: ForeignKey to Company (CASCADE)
- `name`: Profession name (255 chars)
- `description`: Optional description (500 chars max)
- `created_by`: ForeignKey to Recruiter (SET_NULL)
- `created_at`, `updated_at`: Timestamps

**Features**:

- Company-scoped (not globally unique)
- Creator tracking
- Multi-language support

**Use Cases**:

- Custom job titles
- Company role taxonomy
- Vacancy creation forms

---

## Business Logic

### Domain Search Optimization

```python
# list-names endpoint prioritizes exact matches
queryset = queryset.filter(name__istartswith=search)
queryset = queryset.annotate(
    relevance=Case(
        When(name__iexact=search, then=1),  # Exact match first
        default=2,
        output_field=IntegerField(),
    )
).order_by('relevance', 'name')
```

### Validation Rules

**Domain**:

- Name must be unique globally
- Name cannot be empty or whitespace
- Trimmed automatically

**HR Profession**:

- Name required and trimmed
- Description limited to 500 characters
- Company and creator must be valid

---

## Multi-Language Support

Both models support translations via `django-modeltranslation`.

**Translated Fields**:

- `name`, `description`

**Languages**: uz, en, ru

**API Usage**:

```http
GET /api/domains/
Accept-Language: uz
```

Response returns Uzbek translations when available, falls back to English.

---

## Error Responses

**400 Bad Request**:

```json
{
  "name": ["This field is required."],
  "description": ["Description cannot exceed 500 characters."]
}
```

**403 Forbidden**:

```json
{
  "detail": "You do not have permission to perform this action."
}
```

**404 Not Found**:

```json
{
  "error": "Domain not found"
}
```

---

## Security

### Access Control

- Domains: Public viewing, admin-only creation
- Professions: Authenticated users only
- Company scoping for HR professions

### Data Validation

- Input sanitization and trimming
- Length limits enforced
- Uniqueness constraints
- Required field checks

---

## Testing

Run tests:

```bash
python manage.py test apps.domain
```

**Coverage**:

- Model creation and validation
- View permissions and filtering
- Search functionality
- CRUD operations

---

## Admin Interface

### Features

- Full CRUD operations
- Search and filtering
- Bulk duplicate action for domains
- Translation management

**Custom Action**: Duplicate domains (adds "(Copy)" suffix)

---

## Performance

### Optimizations

- Indexed on name fields
- Minimal payload for autocomplete (id + name only)
- No pagination on list-names for speed
- Efficient `istartswith` queries

### Recommendations

- Add caching for frequently accessed domains
- Consider Redis cache for autocomplete

---

## Integration Points

- **Quiz App**: Maps career options to domains
- **Vacancies App**: Uses domains for job categorization
- **Matching System**: Domain-based job-candidate matching

---

This domain system provides flexible professional categorization supporting both global standardization and company-specific customization.
