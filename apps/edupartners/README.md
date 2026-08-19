# EduPartners App

The EduPartners app manages educational institutions and their types, providing a reference system for candidate
educational backgrounds and potential partnerships with educational institutions.

## Overview

This app provides a catalog of educational institutions categorized by type (universities, colleges, schools, etc.) that
can be referenced throughout the platform for candidate profiles, recruitment partnerships, and educational background
verification.

## Features

- **Educational Institution Management**: Complete database of schools, universities, and other educational institutions
- **Institution Categories**: Organized classification system for different types of educational institutions
- **Geographic Information**: Country and city data for institution locations
- **Institution Branding**: Logo and description support for institutional profiles
- **Active Status Management**: Control over which institutions are currently active/visible

## Current Implementation Status

**Models**: ✅ Fully implemented
**Admin Interface**: ✅ Basic admin management
**API Endpoints**: ❌ Not implemented
**Serializers**: ❌ Not implemented
**Views**: ❌ Not implemented

## Models

### EduPartnersType

Classification system for different types of educational institutions.

**Key Fields**:

- `id`: UUID primary key
- `name`: Type name (e.g., "University", "College", "Technical School")

**Examples**:

- University
- College
- Technical School
- High School
- Vocational Institute
- Community College
- Graduate School
- Professional School

**Meta**:

- Verbose names: "Educational Partner Type" / "Educational Partner Types"

### EduPartner

Main model representing educational institutions.

**Key Fields**:

- `id`: UUID primary key
- `name`: Institution name (max 200 chars)
- `edupartner_type`: ForeignKey to EduPartnersType
- `country`: Country location (max 100 chars)
- `city`: City location (max 100 chars)
- `website`: Optional institution website URL
- `logo`: Optional institution logo image
- `description`: Optional text description
- `is_active`: Boolean status flag (default True)
- `created_at`: Auto-generated creation timestamp

**Features**:

- Ordered alphabetically by name
- Support for logo uploads to `edupartner_logos/` directory
- Active/inactive status management
- Geographic location tracking

**String Representation**:

```python
def __str__(self):
    return f"{self.name} - ({self.edupartner_type.name})"
```

## Admin Interface

### EduPartnerTypeAdmin

**Features**:

- **List Display**: ID, name
- **List Links**: ID and name are clickable
- **Search**: Search by ID and name
- **Pagination**: 25 items per page

### EduPartnerAdmin

**Features**:

- **List Display**: ID, name, type, country, city, website, logo, description, active status, creation date
- **Complete Information**: Shows all key fields in list view
- **Basic Management**: Standard Django admin functionality

## Planned API Endpoints

### Public Directory Endpoints

#### List All Educational Institutions

```http
GET /api/edupartners/
```

**Purpose**: Get all active educational institutions

**Authentication**: None required (public directory)

**Query Parameters**:

- `type`: Filter by institution type ID
- `country`: Filter by country
- `city`: Filter by city
- `search`: Search by name or description

**Planned Response**:

```json
[
  {
    "id": "uuid",
    "name": "Harvard University",
    "edupartner_type": {
      "id": "uuid",
      "name": "University"
    },
    "country": "United States",
    "city": "Cambridge",
    "website": "https://harvard.edu",
    "logo": "/media/edupartner_logos/harvard.png",
    "description": "Private Ivy League research university...",
    "is_active": true,
    "created_at": "2023-08-19T10:30:00Z"
  }
]
```

#### Get Institution Details

```http
GET /api/edupartners/{institution_id}/
```

**Purpose**: Get detailed information about a specific institution

**Authentication**: None required

#### List Institution Types

```http
GET /api/edupartners/types/
```

**Purpose**: Get all available institution types

**Planned Response**:

```json
[
  {
    "id": "uuid",
    "name": "University"
  },
  {
    "id": "uuid",
    "name": "College"
  },
  {
    "id": "uuid",
    "name": "Technical School"
  }
]
```

#### Search Institutions

```http
GET /api/edupartners/search/?q=harvard
```

**Purpose**: Search institutions by name or description

**Authentication**: None required

### Admin Endpoints (Future)

#### Create Institution

```http
POST /api/edupartners/
```

**Purpose**: Add new educational institution (admin only)

**Authentication**: Required (Admin only)

**Request Body**:

```json
{
  "name": "MIT",
  "edupartner_type": "university-type-uuid",
  "country": "United States",
  "city": "Cambridge",
  "website": "https://mit.edu",
  "description": "Private research university...",
  "is_active": true
}
```

#### Update Institution

```http
PUT /api/edupartners/{institution_id}/
```

**Purpose**: Update institution information (admin only)

#### Manage Institution Status

```http
PATCH /api/edupartners/{institution_id}/status/
```

**Purpose**: Activate/deactivate institutions

## Integration Possibilities

### Candidate Profiles Integration

```python
# In CandidateProfile model (potential enhancement)
class CandidateProfile(models.Model):
    # ... existing fields ...
    educational_institution = models.ForeignKey(
        'edupartners.EduPartner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Educational institution attended"
    )
```

### Resume Integration

```python
# In Resume education JSON field
{
  "education": [
    {
      "institution_id": "uuid",
      "institution_name": "Harvard University",
      "degree": "Bachelor of Science",
      "field": "Computer Science",
      "graduation_year": 2020,
      "gpa": 3.8
    }
  ]
}
```

### Recruitment Partnerships

```python
# Future RecruitmentPartnership model
class RecruitmentPartnership(models.Model):
    company = models.ForeignKey('authentication.Company', on_delete=models.CASCADE)
    educational_institution = models.ForeignKey('edupartners.EduPartner', on_delete=models.CASCADE)
    partnership_type = models.CharField(max_length=50)  # "Internship", "Graduate Program", etc.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

## Frontend Integration

### Institution Directory

```javascript
// Browse educational institutions
const InstitutionDirectory = () => {
  const [institutions, setInstitutions] = useState([]);
  const [types, setTypes] = useState([]);
  const [filters, setFilters] = useState({
    type: "",
    country: "",
    search: "",
  });

  const fetchInstitutions = async () => {
    const params = new URLSearchParams(filters);
    const response = await fetch(`/api/edupartners/?${params}`);
    setInstitutions(await response.json());
  };

  const fetchTypes = async () => {
    const response = await fetch("/api/edupartners/types/");
    setTypes(await response.json());
  };

  return (
    <div className="institution-directory">
      <InstitutionFilters
        types={types}
        filters={filters}
        onChange={setFilters}
      />
      <InstitutionGrid institutions={institutions} />
    </div>
  );
};
```

### Institution Selector Component

```javascript
// For use in candidate profiles and resume forms
const InstitutionSelector = ({ onSelect, selectedInstitution }) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [suggestions, setSuggestions] = useState([]);

  const searchInstitutions = async (query) => {
    if (query.length < 2) return;

    const response = await fetch(
      `/api/edupartners/search/?q=${encodeURIComponent(query)}`
    );
    const results = await response.json();
    setSuggestions(results);
  };

  useEffect(() => {
    const timeoutId = setTimeout(() => searchInstitutions(searchTerm), 300);
    return () => clearTimeout(timeoutId);
  }, [searchTerm]);

  return (
    <div className="institution-selector">
      <input
        type="text"
        placeholder="Search educational institutions..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      <div className="suggestions">
        {suggestions.map((institution) => (
          <InstitutionSuggestion
            key={institution.id}
            institution={institution}
            onSelect={() => onSelect(institution)}
          />
        ))}
      </div>
    </div>
  );
};
```

## Data Management

### Institution Categories Structure

```
Universities
├── Public Universities
├── Private Universities
├── Research Universities
└── Liberal Arts Colleges

Colleges
├── Community Colleges
├── Technical Colleges
├── Art Colleges
└── Business Colleges

Schools
├── High Schools
├── Middle Schools
├── Elementary Schools
└── International Schools

Specialized Institutions
├── Medical Schools
├── Law Schools
├── Engineering Schools
└── Trade Schools
```

### Sample Data Structure

```python
# Sample institutions
SAMPLE_INSTITUTIONS = [
    {
        "name": "Harvard University",
        "type": "University",
        "country": "United States",
        "city": "Cambridge",
        "website": "https://harvard.edu"
    },
    {
        "name": "Oxford University",
        "type": "University",
        "country": "United Kingdom",
        "city": "Oxford",
        "website": "https://ox.ac.uk"
    },
    {
        "name": "Tashkent State University",
        "type": "University",
        "country": "Uzbekistan",
        "city": "Tashkent",
        "website": "https://tsu.uz"
    }
]
```

## Development Priorities

### Phase 1: Basic API Implementation

1. **Institution CRUD**: Basic create, read, update, delete operations
2. **Type Management**: Institution type endpoints
3. **Search Functionality**: Name and description search
4. **Filtering**: By type, location, and status

### Phase 2: Enhanced Features

1. **Geographic Enhancement**: Better location handling (coordinates, regions)
2. **Institution Rankings**: Rating and ranking system
3. **Partnership Management**: Company-institution partnerships
4. **Verification System**: Institution verification status

### Phase 3: Integration Features

1. **Profile Integration**: Deep integration with candidate profiles
2. **Alumni Networks**: Alumni tracking and networking
3. **Recruitment Partnerships**: Active recruitment relationships
4. **Analytics**: Institution popularity and partnership metrics

## Use Cases

### For Candidates

- **Profile Building**: Select alma mater for profile
- **Resume Creation**: Reference educational background
- **Networking**: Connect with fellow alumni
- **Verification**: Validate educational credentials

### For Recruiters

- **Target Recruitment**: Focus on specific institutions
- **Partnership Management**: Manage university relationships
- **Candidate Sourcing**: Find candidates from target schools
- **Event Planning**: Campus recruitment events

### For Platform

- **Data Consistency**: Standardized institution references
- **Analytics**: Track popular institutions and programs
- **Partnerships**: Facilitate platform-institution relationships
- **Quality Control**: Maintain accurate institution database

## Performance Considerations

### Database Optimization

- **Indexing**: Efficient search on name, country, city
- **Caching**: Cache popular institutions and types
- **Image Optimization**: Optimized logo storage and delivery
- **Geographic Queries**: Efficient location-based filtering

### API Optimization

- **Pagination**: Handle large institution datasets
- **Search Optimization**: Fast text search implementation
- **CDN Integration**: Logo and image delivery via CDN
- **Response Compression**: Minimize API response sizes

This EduPartners system provides a foundation for educational institution management that can support various
recruitment, networking, and verification use cases throughout the job board platform.
