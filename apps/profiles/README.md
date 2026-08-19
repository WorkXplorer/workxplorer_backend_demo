# Profiles App

The Profiles app manages detailed user profiles for candidates, recruiters, and companies, providing rich biographical
and professional information beyond basic authentication data.

## Overview

This app extends the authentication system with comprehensive profile management, allowing users to maintain detailed
professional information, photos, contact details, and organizational data.

## Features

- **Multi-Profile System**: Separate profiles for candidates, recruiters, and companies
- **Rich Profile Data**: Photos, contact information, addresses, and professional details
- **Education Management**: JSON-based education history for candidates
- **Company Branding**: Logo, descriptions, and website information for companies
- **Recruiter Levels**: Hierarchical recruiter classification system
- **Automatic Linking**: Profiles automatically linked to authentication users

## Profile Types

### Candidate Profiles

- Personal information and contact details
- Photo uploads and address information
- Education history (JSON format)
- Linked to resume and application systems

### Recruiter Profiles

- Professional information and experience levels
- Company association and contact details
- Hierarchical level system (Junior, Middle, Senior)
- Photo uploads for professional representation

### Company Profiles

- Branding materials (logos, descriptions)
- Contact information and websites
- Address and location details
- Linked to multiple recruiters and vacancies

## API Endpoints

### Candidate Profile Management

#### Create Candidate Profile

```http
POST /api/profiles/candidate/create/
```

**Purpose**: Create a new candidate profile

**Authentication**: None required (public registration flow)

**Request Body**:

```json
{
  "email": "candidate@example.com",
  "first_name": "John",
  "last_name": "Doe", 
  "phone": "+1-555-0123",
  "candidate_email": "john.doe.personal@gmail.com",
  "address": "123 Main St, San Francisco, CA",
  "education": [
    {
      "institution": "University of California",
      "degree": "Bachelor of Science",
      "field": "Computer Science",
      "graduation_year": 2020,
      "gpa": 3.8
    }
  ]
}
```

**Response** (201 Created):

```json
{
  "id": "uuid",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1-555-0123",
  "candidate_email": "john.doe.personal@gmail.com",
  "address": "123 Main St, San Francisco, CA",
  "photo": null,
  "education": [
    {
      "institution": "University of California",
      "degree": "Bachelor of Science", 
      "field": "Computer Science",
      "graduation_year": 2020,
      "gpa": 3.8
    }
  ]
}
```

**Business Logic**:

- Links profile to existing candidate user via email lookup
- Validates that candidate user exists
- Prevents duplicate profiles for same candidate
- Education stored as flexible JSON structure

---

#### Update Candidate Profile

```http
PUT /api/profiles/candidate/update/
```

**Purpose**: Update current user's candidate profile

**Authentication**: Required (Candidate only)

**Request Body**: Same as create (all fields optional)

**Response** (200 OK): Updated profile data

**Features**:

- Partial updates supported
- Automatic user detection from authentication
- File upload support for photos
- Education array can be completely replaced

---

#### Get Candidate Profile by Email

```http
GET /api/profiles/candidate/retrieve/?email=candidate@example.com
```

**Purpose**: Retrieve specific candidate profile

**Authentication**: Required

**Use Cases**:

- Recruiter viewing applicant profiles
- Admin user management
- Profile verification

**Response** (200 OK):

```json
{
  "id": "uuid",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1-555-0123",
  "candidate_email": "john.doe.personal@gmail.com",
  "photo": "/media/candidate_photos/profile.jpg",
  "address": "123 Main St, San Francisco, CA",
  "education": [
    {
      "institution": "University of California",
      "degree": "Bachelor of Science",
      "field": "Computer Science", 
      "graduation_year": 2020,
      "gpa": 3.8
    }
  ]
}
```

---

### Recruiter Profile Management

#### Create Recruiter Profile

```http
POST /api/profiles/recruiter/create/
```

**Purpose**: Create a new recruiter profile

**Authentication**: None required (registration flow)

**Request Body**:

```json
{
  "recruiter": "recruiter-uuid",
  "first_name": "Sarah",
  "last_name": "Wilson",
  "phone": "+1-555-0456",
  "level": "Senior"
}
```

**Response** (201 Created):

```json
{
  "id": "uuid",
  "recruiter": "recruiter-uuid",
  "company": {
    "id": "company-uuid",
    "name": "TechCorp Inc",
    "tin": "12-3456789"
  },
  "first_name": "Sarah",
  "last_name": "Wilson",
  "phone": "+1-555-0456",
  "photo": null,
  "level": "Senior"
}
```

**Features**:

- Automatically includes company information
- Level validation (Junior, Middle, Senior)
- Photo upload support

---

#### Get Recruiter Profile by Email

```http
GET /api/profiles/recruiter/retrieve/?email=recruiter@company.com
```

**Purpose**: Retrieve specific recruiter profile

**Authentication**: Required

**Response** (200 OK):

```json
{
  "id": "uuid",
  "recruiter": "recruiter-uuid",
  "company": {
    "id": "company-uuid",
    "name": "TechCorp Inc", 
    "tin": "12-3456789"
  },
  "first_name": "Sarah",
  "last_name": "Wilson",
  "phone": "+1-555-0456",
  "photo": "/media/recruiter_photos/sarah.jpg",
  "level": "Senior"
}
```

---

### Universal Profile Endpoints

#### Get My Profile

```http
GET /api/profiles/me/
```

**Purpose**: Get current user's profile (auto-detects type)

**Authentication**: Required

**Response**: Returns appropriate profile type based on user

**Candidate Response** (200 OK):

```json
{
  "id": "uuid",
  "first_name": "John",
  "last_name": "Doe",
  // ... candidate profile fields
}
```

**Recruiter Response** (200 OK):

```json
{
  "id": "uuid", 
  "recruiter": "recruiter-uuid",
  "company": {
    "id": "company-uuid",
    "name": "TechCorp Inc",
    "tin": "12-3456789"
  },
  // ... recruiter profile fields
}
```

---

#### Update My Profile

```http
PUT /api/profiles/me/
```

**Purpose**: Update current user's profile (auto-detects type)

**Authentication**: Required

**Request Body**: Appropriate fields based on user type

**Features**:

- Smart user type detection
- Partial updates supported
- File upload handling for photos
- Automatic profile type routing

---

#### List All Profiles

```http
GET /api/profiles/candidate/
```

```http
GET /api/profiles/recruiter/
```

**Purpose**: List all profiles of specified type

**Authentication**: None required (public directory)

**Use Cases**:

- Public talent directory
- Recruiter directory
- Admin management interface

## Models

### CandidateProfile

Extended profile information for job seekers.

**Key Fields**:

- `id`: UUID primary key
- `candidate`: OneToOne with Candidate user
- `first_name`, `last_name`: Required name fields
- `phone`: Optional contact number
- `candidate_email`: Optional alternative email
- `photo`: Optional profile image
- `address`: Optional location information
- `education`: JSON field for flexible education history

**Education JSON Structure**:

```json
[
  {
    "institution": "University Name",
    "degree": "Bachelor of Science",
    "field": "Computer Science",
    "graduation_year": 2020,
    "gpa": 3.8,
    "honors": ["Magna Cum Laude"],
    "relevant_courses": ["Data Structures", "Algorithms"]
  }
]
```

**Business Rules**:

- One profile per candidate (OneToOne relationship)
- Names are required for professional presentation
- Education history is flexible and extensible
- Photos stored in organized directory structure

### RecruiterProfile

Professional information for hiring managers.

**Key Fields**:

- `id`: UUID primary key
- `recruiter`: ForeignKey to Recruiter user
- `first_name`, `last_name`: Required name fields
- `phone`: Optional contact number
- `photo`: Optional professional headshot
- `level`: Required experience level (Junior/Middle/Senior)

**Level Classifications**:

- **Junior**: Entry-level recruiters, 0-2 years experience
- **Middle**: Experienced recruiters, 2-5 years experience
- **Senior**: Lead recruiters, 5+ years experience

**Company Integration**:

- Automatically includes company data via recruiter relationship
- Company information read-only in profile context
- Enables company-wide recruiter management

### CompanyProfile

Branding and information for organizations.

**Key Fields**:

- `id`: UUID primary key
- `company`: ForeignKey to Company
- `photo`: Logo or company image
- `description`: Company overview and culture
- `address`: Physical location
- `website`: Company website URL

**Use Cases**:

- Job posting branding
- Company pages on job board
- Recruiter context information
- Marketing and presentation materials

## Frontend Integration

### Profile Forms

```javascript
// Dynamic profile form based on user type
const ProfileForm = ({ userType, initialData, onSubmit }) => {
  const [formData, setFormData] = useState(initialData);
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const endpoint = userType === 'candidate' 
      ? '/api/profiles/candidate/update/'
      : '/api/profiles/recruiter/update/';
      
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(formData)
    });
    
    if (response.ok) {
      onSubmit(await response.json());
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {userType === 'candidate' ? (
        <CandidateFields data={formData} onChange={setFormData} />
      ) : (
        <RecruiterFields data={formData} onChange={setFormData} />
      )}
      <button type="submit">Update Profile</button>
    </form>
  );
};
```

### Education Management

```javascript
// Education history component for candidates
const EducationSection = ({ education, onChange }) => {
  const addEducation = () => {
    const newEducation = {
      institution: '',
      degree: '',
      field: '',
      graduation_year: new Date().getFullYear(),
      gpa: null
    };
    onChange([...education, newEducation]);
  };

  const updateEducation = (index, updates) => {
    const updated = education.map((edu, i) => 
      i === index ? { ...edu, ...updates } : edu
    );
    onChange(updated);
  };

  const removeEducation = (index) => {
    onChange(education.filter((_, i) => i !== index));
  };

  return (
    <div className="education-section">
      <h3>Education</h3>
      {education.map((edu, index) => (
        <EducationForm
          key={index}
          education={edu}
          onChange={(updates) => updateEducation(index, updates)}
          onRemove={() => removeEducation(index)}
        />
      ))}
      <button onClick={addEducation}>Add Education</button>
    </div>
  );
};
```

### Photo Upload

```javascript
// Profile photo upload component
const PhotoUpload = ({ currentPhoto, onUpload }) => {
  const handleFileSelect = async (file) => {
    const formData = new FormData();
    formData.append('photo', file);
    
    const response = await fetch('/api/profiles/me/', {
      method: 'PUT',
      credentials: 'include',
      body: formData
    });
    
    if (response.ok) {
      const updatedProfile = await response.json();
      onUpload(updatedProfile.photo);
    }
  };

  return (
    <div className="photo-upload">
      {currentPhoto && (
        <img src={currentPhoto} alt="Profile" className="current-photo" />
      )}
      <input
        type="file"
        accept="image/*"
        onChange={(e) => handleFileSelect(e.target.files[0])}
      />
    </div>
  );
};
```

## Business Logic

### Profile Creation Flow

1. **User Registration**: User creates account via authentication app
2. **Profile Prompt**: System prompts for profile completion
3. **Profile Creation**: User submits profile information
4. **User Linking**: Profile automatically linked via email lookup
5. **Validation**: System validates all required fields
6. **Storage**: Profile saved with appropriate user association

### Profile Auto-Detection

```python
def get_user_profile(user):
    """Automatically detect and return appropriate profile"""
    if user.is_candidate:
        return CandidateProfile.objects.filter(candidate=user).first()
    elif user.is_recruiter:
        return RecruiterProfile.objects.filter(recruiter=user).first()
    return None
```

### Education Flexibility

The JSON education field allows for:

- Multiple degrees and certifications
- Flexible field names and structures
- Additional metadata (honors, courses, projects)
- Easy extension without schema changes
- Complex querying when needed

## Error Handling

### Profile Creation Errors

```json
// Candidate not found
{
  "email": ["No candidate found with this email"]
}

// Duplicate profile
{
  "email": ["Profile already exists for this candidate"]
}

// Missing required fields
{
  "first_name": ["This field is required."],
  "last_name": ["This field is required."]
}
```

### File Upload Errors

```json
// File too large
{
  "photo": ["File size too large. Maximum size is 5MB."]
}

// Invalid file type
{
  "photo": ["Invalid file type. Please upload an image."]
}
```

### Permission Errors

```json
// Wrong user type
{
  "detail": "User is not a candidate"
}

// Profile not found
{
  "detail": "Profile not found for this candidate"
}
```

## Performance & Security

### Database Optimization

- **Indexes**: Strategic indexes on name fields for searching
- **Select Related**: Automatic company data loading for recruiters
- **File Storage**: Organized directory structure for uploads
- **JSON Querying**: PostgreSQL JSON field support for education searches

### Security Features

- **User Scoping**: Users can only access their own profiles
- **File Validation**: Image upload validation and sanitization
- **Input Sanitization**: All text fields properly validated
- **Access Control**: Role-based profile access restrictions

### File Management

- **Organized Storage**: Photos stored in type-specific directories
- **Size Limits**: Configurable file size restrictions
- **Format Validation**: Image format verification
- **URL Generation**: Automatic media URL generation

This profiles system provides comprehensive user information management with flexible data structures and robust
security controls.