# Vacancies App

The Vacancies app manages job postings, allowing recruiters to create and manage job listings with detailed skill
requirements, while providing candidates with a searchable job board.

## Overview

This app handles the complete job posting lifecycle from creation by recruiters to browsing by candidates. It includes
sophisticated skill requirement management, salary ranges, and employment type categorization.

## Features

- **Job Posting Management**: Create, update, and manage job vacancies
- **Skill Requirements**: Detailed skill specifications with proficiency levels
- **Employment Types**: Full-time, part-time, contract, and internship positions
- **Salary Management**: Flexible salary range specifications
- **Company Association**: Automatic company linkage for recruiters
- **Public Job Board**: Searchable listings for candidates
- **Advanced Search & Filtering**: Search by keywords, company address, salary, employment type, skills, and more
- **Sorting**: Order results by date, salary, or title
- **Pagination**: Efficient browsing of large job listings

## Search and Filtering

The vacancies API now includes comprehensive search and filtering capabilities, making it easy for students to find
relevant job opportunities. For detailed documentation on all search features, see [SEARCH_GUIDE.md](./SEARCH_GUIDE.md).

**Quick Examples:**

Search for jobs:

```
GET /api/v1/vacancies/?search=python developer
```

Filter by company address and employment type:

```
GET /api/v1/vacancies/?location=tashkent&employment_type=FULL_TIME
```

Filter by salary range:

```
GET /api/v1/vacancies/?salary_min=60000&salary_max_lte=120000
```

Sort by newest first:

```
GET /api/v1/vacancies/?ordering=-created_at
```

Combine multiple filters:

```
GET /api/v1/vacancies/?search=engineer&location=tashkent&employment_type=FULL_TIME&salary_min=100000&ordering=-created_at
```

## API Endpoints

### Public Endpoints (Candidates & General)

#### List All Active Vacancies

```http
GET /api/vacancies/
```

**Purpose**: Browse all available job postings

**Authentication**: None required

**Query Parameters**:

The vacancy list endpoint supports comprehensive search and filtering:

- `search` - Search across title and company name
- `location` - Filter by company address (case-insensitive partial match)
- `employment_type` - Filter by type: FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP
- `salary_min` - Minimum salary at least this amount
- `salary_max_lte` - Maximum salary at most this amount
- `company_name` - Filter by company name (case-insensitive partial match)
- `company` - Filter by company UUID
- `skill` - Filter by required skill ID
- `created_after` - Jobs posted after this date
- `created_before` - Jobs posted before this date
- `ordering` - Sort results by: created_at, title (prefix with `-` for descending)

For comprehensive documentation and examples, see [SEARCH_GUIDE.md](./SEARCH_GUIDE.md).

**Response** (200 OK):

```json
[
  {
    "id": "uuid",
    "title": "Senior Software Engineer",
    "company_name": "TechCorp Inc",
    "recruiter_email": "hr@techcorp.com",
    "employment_type": "FULL_TIME",
    "company_address": "Tashkent, Uzbekistan",
    "description": "We are looking for a senior software engineer...",
    "created_at": "2023-08-19T10:30:00Z",
    "updated_at": "2023-08-19T10:30:00Z",
    "vacancy_skills": [
      {
        "skill_id": "uuid",
        "skill_name": "Python",
        "is_required": true,
        "minimum_years": 5,
        "proficiency_level": "ADVANCED"
      },
      {
        "skill_id": "uuid",
        "skill_name": "Django",
        "is_required": true,
        "minimum_years": 3,
        "proficiency_level": "INTERMEDIATE"
      },
      {
        "skill_id": "uuid",
        "skill_name": "React",
        "is_required": false,
        "minimum_years": 2,
        "proficiency_level": "INTERMEDIATE"
      }
    ]
  }
]
```

**Features**:

- Only shows active vacancies (`is_active=True`)
- Includes computed salary range display
- Shows required and optional skills with proficiency levels
- Optimized queries with `select_related()` for performance

---

### Recruiter Endpoints

#### Create New Vacancy

```http
POST /api/vacancies/create/
```

**Purpose**: Create a new job posting

**Authentication**: Required (Recruiter only)

**Authorization**: Must be associated with a company

**Request Body**:

```json
{
  "title": "Senior Software Engineer",
  "description": "We are looking for an experienced software engineer to join our team...",
  "employment_type": "FULL_TIME",
  "salary_min": 120000.0,
  "salary_max": 180000.0,
  "skills_data": [
    {
      "skill_id": "uuid",
      "is_required": true,
      "minimum_years": 5,
      "proficiency_level": "ADVANCED"
    },
    {
      "skill_id": "uuid",
      "is_required": false,
      "minimum_years": 2,
      "proficiency_level": "INTERMEDIATE"
    }
  ]
}
```

**Response** (201 Created):

```json
{
  "message": "Vacancy created successfully",
  "vacancy": {
    "id": "uuid",
    "title": "Senior Software Engineer",
    "company": "company-uuid",
    "company_name": "TechCorp Inc",
    "created_by": "recruiter-uuid",
    "recruiter_email": "hr@techcorp.com",
    "employment_type": "FULL_TIME",
    "company_address": "Tashkent, Uzbekistan",
    "description": "We are looking for an experienced...",
    "is_active": true,
    "created_at": "2023-08-19T10:30:00Z",
    "updated_at": "2023-08-19T10:30:00Z",
    "vacancy_skills": [
      {
        "skill_id": "uuid",
        "skill_name": "Python",
        "is_required": true,
        "minimum_years": 5,
        "proficiency_level": "ADVANCED"
      }
    ]
  }
}
```

**Automatic Behavior**:

- `created_by` set from authenticated recruiter
- `company` set from recruiter's company
- `is_active` defaults to `true`
- Skills validated for existence and proficiency levels

**Validation Rules**:

- `title` is required (max 240 characters)
- `description` is required
- `employment_type` must be valid choice
- `salary_min` cannot exceed `salary_max`
- Skills must exist in database
- Proficiency levels must be valid

---

#### Get My Vacancies

```http
GET /api/vacancies/my-vacancies/
```

**Purpose**: List all vacancies created by the current recruiter

**Authentication**: Required (Recruiter only)

**Response** (200 OK):

```json
[
  {
    "id": "uuid",
    "title": "Senior Software Engineer",
    "company_name": "TechCorp Inc",
    "employment_type": "FULL_TIME",
    "company_address": "Tashkent, Uzbekistan",
    "is_active": true,
    "created_at": "2023-08-19T10:30:00Z",
    "vacancy_skills": [
      // skill requirements
    ]
  }
]
```

**Use Cases**:

- Recruiter dashboard
- Vacancy management interface
- Performance tracking
- Edit/update existing postings

---

## Models

### Vacancy

Main model representing a job posting.

**Key Fields**:

- `id`: UUID primary key
- `title`: Job title (max 240 chars)
- `description`: Detailed job description (required)
- `company`: ForeignKey to Company (auto-set)
- `created_by`: ForeignKey to Recruiter (auto-set)
- `employment_type`: Choice field (FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP)
- `salary_min/salary_max`: Optional salary range
- `is_active`: Boolean for publication status
- `required_skills`: ManyToMany through VacancySkill

**Business Rules**:

- Recruiter can only create vacancies for their company
- `created_by` and `company` are automatically set on creation
- Only active vacancies appear in public listings
- Salary validation ensures min ≤ max

**Database Optimization**:

- Indexes on common query fields (company, created_by, employment_type, is_active)
- Ordering by creation date (newest first)

### VacancySkill

Through model for skill requirements.

**Key Fields**:

- `vacancy`: ForeignKey to Vacancy
- `skill`: ForeignKey to Skill
- `is_required`: Boolean (required vs nice-to-have)
- `minimum_years`: Integer (experience requirement)
- `proficiency_level`: Choice field (BEGINNER, INTERMEDIATE, ADVANCED, EXPERT)

**Constraints**:

- Unique together (vacancy, skill) - prevents duplicates
- Minimum years defaults to 0

**Use Cases**:

- Skill-based job matching
- Application filtering
- Candidate skill gap analysis
- Recruiter skill planning

## Employment Types

```python
EMPLOYMENT_TYPES = [
    ("FULL_TIME", "Full Time"),      # Standard 40-hour positions
    ("PART_TIME", "Part Time"),      # Reduced hour positions
    ("CONTRACT", "Contract"),        # Fixed-term engagements
    ("INTERNSHIP", "Internship"),    # Student/entry-level programs
]
```

## Skill Proficiency Levels

```python
PROFICIENCY_LEVELS = [
    ("BEGINNER", "Beginner"),           # 0-1 years, basic knowledge
    ("INTERMEDIATE", "Intermediate"),   # 2-4 years, working proficiency
    ("ADVANCED", "Advanced"),          # 5+ years, expert level
    ("EXPERT", "Expert"),              # Industry recognized expertise
]
```

## Frontend Integration

### Job Board Display

```javascript
// Fetch and display all available jobs
const fetchJobs = async (filters = {}) => {
  const params = new URLSearchParams(filters);
  const response = await fetch(`/api/vacancies/?${params}`, {
    credentials: "include",
  });
  return response.json();
};

// Example job card component data
const JobCard = ({ vacancy }) => (
  <div className="job-card">
    <h3>{vacancy.title}</h3>
    <p>{vacancy.company_name}</p>
    <p>{vacancy.company_address}</p>
    <div className="skills">
      {vacancy.vacancy_skills.map((skill) => (
        <span
          key={skill.skill_id}
          className={skill.is_required ? "required" : "optional"}
        >
          {skill.skill_name} ({skill.proficiency_level})
        </span>
      ))}
    </div>
  </div>
);
```

### Recruiter Vacancy Creation

```javascript
// Create new job posting
const createVacancy = async (vacancyData) => {
  const response = await fetch("/api/vacancies/create/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(vacancyData),
  });

  if (response.ok) {
    const result = await response.json();
    console.log("Vacancy created:", result.vacancy);
    return result.vacancy;
  }
};

// Example form data structure
const vacancyFormData = {
  title: "Senior Frontend Developer",
  description: "Join our team to build amazing user experiences...",
  employment_type: "FULL_TIME",
  salary_min: 90000,
  salary_max: 130000,
  skills_data: [
    {
      skill_id: "react-skill-uuid",
      is_required: true,
      minimum_years: 4,
      proficiency_level: "ADVANCED",
    },
    {
      skill_id: "typescript-skill-uuid",
      is_required: true,
      minimum_years: 2,
      proficiency_level: "INTERMEDIATE",
    },
    {
      skill_id: "nodejs-skill-uuid",
      is_required: false,
      minimum_years: 1,
      proficiency_level: "BEGINNER",
    },
  ],
};
```

### Skill Management Interface

```javascript
// Component for managing skill requirements
const SkillRequirements = ({ skills, onChange }) => {
  const addSkill = (skillId) => {
    const newSkill = {
      skill_id: skillId,
      is_required: true,
      minimum_years: 1,
      proficiency_level: "INTERMEDIATE",
    };
    onChange([...skills, newSkill]);
  };

  const updateSkill = (index, updates) => {
    const updated = skills.map((skill, i) =>
      i === index ? { ...skill, ...updates } : skill
    );
    onChange(updated);
  };

  const removeSkill = (index) => {
    onChange(skills.filter((_, i) => i !== index));
  };

  return (
    <div className="skill-requirements">
      {skills.map((skill, index) => (
        <SkillRequirementRow
          key={index}
          skill={skill}
          onUpdate={(updates) => updateSkill(index, updates)}
          onRemove={() => removeSkill(index)}
        />
      ))}
      <SkillSelector onAdd={addSkill} />
    </div>
  );
};
```

## Business Logic

### Vacancy Creation Process

1. **Authentication Check**: Verify user is a recruiter
2. **Company Validation**: Ensure recruiter has associated company
3. **Data Validation**: Validate all required fields and constraints
4. **Skill Processing**: Validate and create skill requirements
5. **Auto-Population**: Set `created_by` and `company` from user context
6. **Database Creation**: Save vacancy and associated skills
7. **Response**: Return complete vacancy data with computed fields

### Skill Requirement Logic

- **Required vs Optional**: Affects application scoring/matching
- **Experience Levels**: Used for candidate filtering
- **Proficiency Mapping**: Guides candidate skill assessment
- **Bulk Operations**: Efficient skill creation using `bulk_create()`

## Error Handling

### Validation Errors

```json
// Missing required fields
{
  "title": ["This field is required."],
  "description": ["This field is required."]
}

// Invalid skill data
{
  "skills_data": ["Skill with ID abc-123 does not exist"]
}

// Invalid salary range
{
  "salary_max": ["Maximum salary cannot be less than minimum salary"]
}
```

### Permission Errors

```json
// Non-recruiter trying to create vacancy
{
  "error": "Only recruiters can create vacancies"
}

// Recruiter without company
{
  "error": "Recruiter must be associated with a company to create vacancies"
}
```

## Performance Considerations

### Database Optimization

- **Select Related**: All list views use `select_related('company', 'created_by')`
- **Prefetch Related**: Skills loaded efficiently with `prefetch_related()`
- **Indexes**: Strategic indexes on frequently queried fields
- **Bulk Operations**: Skill creation uses `bulk_create()` for performance

### API Optimization

- **Computed Fields**: Salary range calculated in serializer, not database
- **Read-Only Fields**: Automatic fields marked as read-only
- **Pagination**: Built-in DRF pagination for large datasets
- **Filtering**: Efficient filtering by employment type, company address, etc.

## Security Features

### Access Control

- **Role-Based**: Only recruiters can create/manage vacancies
- **Company Scoping**: Recruiters can only create for their company
- **Automatic Context**: User context prevents privilege escalation
- **Public Safety**: Only active vacancies visible to candidates

### Data Validation

- **Input Sanitization**: All text fields validated and sanitized
- **Skill Validation**: Skills must exist before being referenced
- **Range Validation**: Salary min/max relationship enforced
- **Length Limits**: Title and description length constraints

This vacancies system provides a robust foundation for job posting management with sophisticated skill matching
capabilities and strong security controls.
