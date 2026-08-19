# Resumes App

The Resumes app manages candidate resume creation, storage, and skill tracking, providing a comprehensive system for
professional experience documentation and skill-based job matching.

## Overview

This app allows candidates to create multiple resume versions with detailed skill specifications, work experience, and
contact information. It serves as the foundation for job applications and skill-based matching with vacancies.

## Features

- **Multiple Resume Versions**: Candidates can maintain different resumes for different roles
- **Skill Management**: Detailed skill tracking with proficiency levels and experience years
- **Work Experience**: Complete employment history with descriptions
- **Contact Information**: Multiple contact methods and professional links
- **Application Integration**: Resumes linked to job applications
- **Skill Matching**: Foundation for candidate-vacancy matching algorithms

## Current Implementation Status

**Models**: ✅ Fully implemented and functional
**Admin Interface**: ✅ Comprehensive admin management
**Basic API**: ⚠️ Partially implemented (needs enhancement)
**Advanced Features**: ❌ Pending implementation

## API Endpoints

### Current Endpoints

#### List All Resumes

```http
GET /api/resumes/
```

**Purpose**: Get all resumes in the system

**Authentication**: None required

**Response** (200 OK):

```json
[
  {
    "id": "uuid",
    "title": "Senior Software Engineer Resume",
    "description": "Experienced full-stack developer...",
    "skills": ["skill-uuid-1", "skill-uuid-2"],
    "created_at": "2023-08-19T10:30:00Z"
  }
]
```

#### Create Resume

```http
POST /api/resumes/create/
```

**Purpose**: Create a new resume

**Authentication**: Required

**Request Body**:

```json
{
  "email": "candidate@example.com",
  "title": "Senior Software Engineer Resume",
  "description": "Experienced full-stack developer with 5+ years in web technologies",
  "skills": ["skill-uuid-1", "skill-uuid-2"]
}
```

**Response** (201 Created):

```json
{
  "id": "uuid",
  "title": "Senior Software Engineer Resume",
  "description": "Experienced full-stack developer...",
  "skills": ["skill-uuid-1", "skill-uuid-2"],
  "created_at": "2023-08-19T10:30:00Z"
}
```

## Models

### Resume

Primary model for storing resume information.

**Key Fields**:

- `id`: UUID primary key for security
- `created_at`: Timestamp for resume creation
- `candidate`: ForeignKey to Candidate (who owns this resume)
- `title`: Resume title/headline (max 140 chars)
- `description`: Detailed resume description
- `skills`: ManyToMany relationship through ResumeSkill

**Database Optimization**:

- Indexes on candidate, created_at, and title fields
- Ordering by creation date (newest first)

### ResumeSkill

Through model linking resumes to skills with proficiency details.

**Key Fields**:

- `resume`: ForeignKey to Resume
- `skill`: ForeignKey to Skill
- `minimum_years`: Experience years with this skill (default 0)
- `proficiency_level`: Skill proficiency level

**Proficiency Levels**:

- `BEGINNER`: Basic knowledge
- `INTERMEDIATE`: Working proficiency (default)
- `ADVANCED`: Expert level
- `EXPERT`: Industry recognized expertise

**Constraints**:

- Unique constraint on (resume, skill) - prevents duplicates

### ResumeExperience

Work history entries for each resume.

**Key Fields**:

- `resume`: ForeignKey to Resume
- `company`: Company name (max 140 chars)
- `role`: Job title/role (max 140 chars)
- `start_date`: Employment start date (optional)
- `end_date`: Employment end date (optional)
- `description`: Job description and achievements
- `years`: Total years of experience (default 0)

**Features**:

- Ordered by start_date (newest first)
- Supports current positions (end_date can be null)

### ResumeContact

Contact information and professional links.

**Key Fields**:

- `resume`: ForeignKey to Resume
- `type`: Contact type (EMAIL, PHONE, LINKEDIN, GITHUB, PORTFOLIO)
- `value`: Contact value (email address, phone number, URL, etc.)

**Contact Types**:

- `EMAIL`: Email address
- `PHONE`: Phone number
- `LINKEDIN`: LinkedIn profile URL
- `GITHUB`: GitHub profile URL
- `PORTFOLIO`: Portfolio website URL

**Constraints**:

- Unique together (resume, type, value) - prevents duplicate contacts

## Admin Interface

### Resume Admin

**Features**:

- **List Display**: Title, candidate, creation date, skills preview
- **Filtering**: By creation date, candidate
- **Search**: Title, description, candidate username
- **Inlines**: Skills, experiences, and contacts management
- **Date Hierarchy**: Easy browsing by creation date
- **Skills Preview**: Shows first 5 skills with proficiency levels

### ResumeSkill Admin

**Features**:

- **List Display**: Resume, skill, years, proficiency level
- **Search**: Resume title, skill name
- **Filtering**: By proficiency level
- **Autocomplete**: Skill selection with search

### ResumeExperience Admin

**Features**:

- **List Display**: Resume, company, role, dates, years
- **Search**: Company, role, resume title
- **Filtering**: By company, start date

### ResumeContact Admin

**Features**:

- **List Display**: Resume, contact type, value
- **Search**: Value, resume title
- **Filtering**: By contact type

## Integration with Applications

### Resume Selection in Applications

```python
# In JobApplication model
resume_used = models.ForeignKey(
    'resumes.Resume',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='applications',
    help_text='The specific resume version used for this application'
)
```

### Application Flow

1. **Resume Selection**: When applying, candidates can choose which resume to use
2. **Version Tracking**: Applications track which resume version was submitted
3. **Historical Integrity**: Resume changes don't affect past applications
4. **Multiple Versions**: Candidates can maintain role-specific resumes

## Database Relationships

```
Candidate (1) ←→ (∞) Resume
Resume (1) ←→ (∞) ResumeSkill ←→ (1) Skill
Resume (1) ←→ (∞) ResumeExperience  
Resume (1) ←→ (∞) ResumeContact
Resume (1) ←→ (∞) JobApplication
```

## Current Serializer

### ResumeSerializer

Basic serializer for resume CRUD operations.

**Fields**:

- `id`: Resume UUID
- `title`: Resume title
- `description`: Resume description
- `skills`: List of skill UUIDs
- `email`: Write-only field for candidate lookup
- `created_at`: Creation timestamp

**Create Process**:

1. Extract email from request data
2. Find candidate by email
3. Link resume to candidate
4. Create resume record

## Needed Enhancements

### Missing API Endpoints

#### Enhanced Resume Detail

```http
GET /api/resumes/{resume_id}/
```

**Should Include**:

- Full resume details
- Complete skill information with proficiency levels
- Work experience history
- Contact information
- Related applications count

#### Update Resume

```http
PUT /api/resumes/{resume_id}/
```

**Should Support**:

- Partial updates
- Skill management
- Experience updates
- Contact information updates

#### My Resumes (Candidate-specific)

```http
GET /api/resumes/my-resumes/
```

**Should Return**:

- Only current candidate's resumes
- Resume usage statistics
- Application counts per resume

### Enhanced Serializers Needed

#### ResumeSkillSerializer

```python
class ResumeSkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    skill_category = serializers.CharField(source='skill.category.name', read_only=True)
    
    class Meta:
        model = ResumeSkill
        fields = ['skill_id', 'skill_name', 'skill_category', 'minimum_years', 'proficiency_level']
```

#### ResumeExperienceSerializer

```python
class ResumeExperienceSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()
    
    class Meta:
        model = ResumeExperience
        fields = ['company', 'role', 'start_date', 'end_date', 'years', 'description', 'is_current']
        
    def get_is_current(self, obj):
        return obj.end_date is None
```

#### ResumeContactSerializer

```python
class ResumeContactSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    
    class Meta:
        model = ResumeContact
        fields = ['type', 'type_display', 'value']
```

#### Enhanced ResumeDetailSerializer

```python
class ResumeDetailSerializer(serializers.ModelSerializer):
    resume_skills = ResumeSkillSerializer(many=True, read_only=True)
    experiences = ResumeExperienceSerializer(many=True, read_only=True)
    contacts = ResumeContactSerializer(many=True, read_only=True)
    applications_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Resume
        fields = [
            'id', 'title', 'description', 'created_at',
            'resume_skills', 'experiences', 'contacts', 'applications_count'
        ]
```

## Frontend Integration

### Resume Builder Interface

```javascript
// Enhanced resume management
const ResumeManager = () => {
  const [resumes, setResumes] = useState([]);
  const [currentResume, setCurrentResume] = useState(null);

  const fetchResumes = async () => {
    const response = await fetch('/api/resumes/my-resumes/', {
      credentials: 'include'
    });
    setResumes(await response.json());
  };

  const createResume = async (resumeData) => {
    const response = await fetch('/api/resumes/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(resumeData)
    });
    
    if (response.ok) {
      const newResume = await response.json();
      setResumes([...resumes, newResume]);
      return newResume;
    }
  };

  return (
    <div className="resume-manager">
      <ResumeList resumes={resumes} onSelect={setCurrentResume} />
      {currentResume && (
        <ResumeEditor 
          resume={currentResume} 
          onSave={updateResume}
          onDelete={deleteResume}
        />
      )}
    </div>
  );
};
```

### Skill Management Component

```javascript
// Skills section for resume builder
const ResumeSkillsSection = ({ resumeId, skills, onChange }) => {
  const [availableSkills, setAvailableSkills] = useState([]);
  
  const addSkill = async (skillId, proficiencyLevel, years) => {
    const response = await fetch(`/api/resumes/${resumeId}/skills/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        skill_id: skillId,
        proficiency_level: proficiencyLevel,
        minimum_years: years
      })
    });
    
    if (response.ok) {
      const updatedSkills = await response.json();
      onChange(updatedSkills);
    }
  };

  return (
    <div className="resume-skills">
      <h3>Skills</h3>
      {skills.map(skill => (
        <SkillEntry 
          key={skill.skill_id}
          skill={skill}
          onUpdate={(updates) => updateSkill(skill.skill_id, updates)}
          onRemove={() => removeSkill(skill.skill_id)}
        />
      ))}
      <SkillSelector onAdd={addSkill} availableSkills={availableSkills} />
    </div>
  );
};
```

## Development Priorities

### Phase 1: Enhanced API

1. **Complete CRUD Operations**: Update, delete, detailed view endpoints
2. **Enhanced Serializers**: Include related data (skills, experience, contacts)
3. **Candidate-Specific Views**: My resumes, usage statistics
4. **Permission Classes**: Candidate-only access control

### Phase 2: Advanced Resume Features

1. **Resume Templates**: Predefined resume formats and structures
2. **Skill Suggestions**: AI-powered skill recommendations based on job descriptions
3. **Experience Validation**: Automatic date validation and duration calculations
4. **Resume Analytics**: View counts, application success rates

### Phase 3: Integration Features

1. **Enhanced Application Integration**: Better resume selection UX
2. **Skill Matching Algorithms**: Resume-vacancy compatibility scoring
3. **Resume Import/Export**: PDF generation, LinkedIn import
4. **Version Management**: Resume versioning and change tracking

## Performance Considerations

### Database Optimization

- **Indexes**: Strategic indexes on frequently queried fields
- **Select Related**: Optimize queries for skills and experiences
- **Prefetch Related**: Efficient loading of related data
- **Bulk Operations**: Bulk skill and experience updates

### Caching Strategy

- **Resume Cache**: Cache complete resume data for applications
- **Skill Data**: Cache skill information for faster lookups
- **Statistics**: Cache resume performance metrics

## Security Features

### Access Control

- **Owner-Only Access**: Candidates can only manage their own resumes
- **Application Integrity**: Resume versions preserved in applications
- **Skill Validation**: Only valid skills can be added to resumes
- **Input Sanitization**: All text fields properly validated

### Data Protection

- **UUID Keys**: Prevent ID enumeration attacks
- **Audit Trail**: Track resume modifications
- **Privacy Controls**: Control resume visibility settings
- **Safe Deletion**: Prevent deletion of resumes used in active applications

## Error Handling

### Validation Errors

```json
// Missing candidate
{
  "email": ["No candidate found"]
}

// Duplicate skills
{
  "skills": ["Skill 'Python' already exists on this resume"]
}

// Invalid proficiency level
{
  "proficiency_level": ["Invalid choice. Must be one of: BEGINNER, INTERMEDIATE, ADVANCED, EXPERT"]
}
```

### Permission Errors

```json
// Unauthorized access
{
  "detail": "You can only manage your own resumes"
}

// Resume not found
{
  "detail": "Resume not found or access denied"
}
```

This enhanced resumes system provides a solid foundation for professional profile management with strong integration
capabilities for the job application process and clear pathways for advanced features implementation.