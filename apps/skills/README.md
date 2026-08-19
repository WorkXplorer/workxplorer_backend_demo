# Skills App

The Skills app provides a centralized skill taxonomy system that powers skill-based matching between candidates and job
vacancies, with support for skill categories, synonyms, and standardized skill definitions.

## Overview

This app serves as the foundation for the entire skill-based matching system in the platform. It provides standardized
skill definitions that are used by both resumes and vacancy requirements, enabling intelligent job matching and skill
gap analysis.

## Features

- **Centralized Skill Taxonomy**: Standardized skill definitions across the platform
- **Skill Categories**: Organized skill grouping (Programming, Languages, Soft Skills, etc.)
- **Skill Synonyms**: Handle different names for the same skill (JS vs JavaScript)
- **Hierarchical Organization**: Category-based skill organization
- **Cross-Platform Integration**: Used by resumes, vacancies, and applications

## Models

### SkillCategory

Organizational structure for grouping related skills.

**Key Fields**:

- `id`: UUID primary key
- `name`: Category name (unique)
- `description`: Category description
- `created_at`: Creation timestamp

**Examples**:

- Programming Languages
- Frameworks & Libraries
- Databases
- Cloud Platforms
- Soft Skills
- Languages
- Certifications

### Skill

Core skill definitions used throughout the platform.

**Key Fields**:

- `id`: UUID primary key
- `name`: Skill name (unique)
- `category`: ForeignKey to SkillCategory (optional)
- `description`: Skill description
- `created_at`: Creation timestamp

**Examples**:

- Python (Programming Languages)
- Django (Frameworks & Libraries)
- PostgreSQL (Databases)
- AWS (Cloud Platforms)
- Leadership (Soft Skills)

### SkillSynonym

Alternative names for the same skill.

**Key Fields**:

- `skill`: ForeignKey to Skill
- `synonym`: JSON field for alternative names

**Use Cases**:

- JavaScript ↔ JS
- React.js ↔ React ↔ ReactJS
- Node.js ↔ NodeJS ↔ Node
- PostgreSQL ↔ Postgres ↔ PSQL

## Current Implementation Status

**Note**: This app currently has models and admin interface implemented, but **API endpoints are not yet created**. The
models are fully functional and integrated with resumes and vacancies systems.

## Admin Interface

### SkillCategory Admin

- **List Display**: Name, description, creation date
- **Search Fields**: Name
- **Ordering**: Alphabetical by name
- **Read-only Fields**: Creation timestamp

### Skill Admin

- **List Display**: Name, category, description, creation date
- **Search Fields**: Name
- **Filtering**: By category
- **Ordering**: Category name, then skill name
- **Change Links**: Direct links to edit skills

### SkillSynonym Admin

- **List Display**: Skill, synonym
- **Search**: By skill name and synonym
- **Inline Editing**: Manage synonyms within skill admin

## Integration with Other Apps

### Resumes Integration

```python
# ResumeSkill model uses skills
class ResumeSkill(models.Model):
    skill = models.ForeignKey('skills.Skill', on_delete=models.CASCADE)
    proficiency_level = models.CharField(...)
    minimum_years = models.PositiveIntegerField(...)
```

### Vacancies Integration

```python
# VacancySkill model uses skills
class VacancySkill(models.Model):
    skill = models.ForeignKey('skills.Skill', on_delete=models.CASCADE)
    is_required = models.BooleanField(...)
    proficiency_level = models.CharField(...)
```

## Planned API Endpoints

### Skill Management

#### List All Skills

```http
GET /api/skills/
```

**Purpose**: Get all available skills with categories

**Authentication**: None required (public reference data)

**Planned Response**:

```json
[
  {
    "id": "uuid",
    "name": "Python",
    "category": {
      "id": "uuid",
      "name": "Programming Languages",
      "description": "Programming and scripting languages"
    },
    "description": "High-level programming language known for its simplicity and versatility",
    "synonyms": ["python3", "py"],
    "created_at": "2023-08-19T10:30:00Z"
  },
  {
    "id": "uuid",
    "name": "JavaScript",
    "category": {
      "id": "uuid",
      "name": "Programming Languages"
    },
    "description": "Dynamic programming language for web development",
    "synonyms": ["JS", "ECMAScript", "ES6"],
    "created_at": "2023-08-19T10:30:00Z"
  }
]
```

#### Search Skills

```http
GET /api/skills/search/?q=python
```

**Purpose**: Search skills by name or synonym

**Authentication**: None required

**Planned Response**:

```json
[
  {
    "id": "uuid",
    "name": "Python",
    "category_name": "Programming Languages",
    "match_type": "exact", // "exact", "synonym", "partial"
    "description": "High-level programming language..."
  }
]
```

#### Get Skills by Category

```http
GET /api/skills/category/{category_id}/
```

**Purpose**: Get all skills in a specific category

**Authentication**: None required

#### List All Categories

```http
GET /api/skills/categories/
```

**Purpose**: Get all skill categories

**Authentication**: None required

**Planned Response**:

```json
[
  {
    "id": "uuid",
    "name": "Programming Languages",
    "description": "Programming and scripting languages",
    "skills_count": 25,
    "created_at": "2023-08-19T10:30:00Z"
  },
  {
    "id": "uuid",
    "name": "Frameworks & Libraries",
    "description": "Software frameworks and libraries",
    "skills_count": 40,
    "created_at": "2023-08-19T10:30:00Z"
  }
]
```

### Admin Endpoints (Future)

#### Create Skill

```http
POST /api/skills/
```

**Purpose**: Create new skill (admin only)

**Authentication**: Required (Admin only)

**Planned Request Body**:

```json
{
  "name": "TypeScript",
  "category": "category-uuid",
  "description": "Typed superset of JavaScript",
  "synonyms": ["TS", "typescript"]
}
```

#### Update Skill

```http
PUT /api/skills/{skill_id}/
```

**Purpose**: Update skill information (admin only)

#### Merge Skills

```http
POST /api/skills/{skill_id}/merge/
```

**Purpose**: Merge duplicate skills (admin only)

**Planned Request Body**:

```json
{
  "merge_with": "target-skill-uuid",
  "update_references": true
}
```

## Skill Taxonomy Structure

### Programming Languages

- Python, JavaScript, Java, C#, C++, Go, Rust, PHP, Ruby, Swift, Kotlin

### Frameworks & Libraries

- React, Angular, Vue.js, Django, Flask, Spring Boot, Express.js, Laravel, Rails

### Databases

- PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, Cassandra, Oracle

### Cloud Platforms

- AWS, Azure, Google Cloud, Docker, Kubernetes, Terraform, Jenkins

### Soft Skills

- Leadership, Communication, Problem Solving, Team Management, Project Management

### Languages

- English, Spanish, French, German, Chinese, Japanese, Arabic

## Synonym Management

### Common Synonym Patterns

```json
{
  "JavaScript": ["JS", "ECMAScript", "ES6", "ES2015"],
  "React": ["React.js", "ReactJS"],
  "Node.js": ["NodeJS", "Node"],
  "PostgreSQL": ["Postgres", "PSQL"],
  "Amazon Web Services": ["AWS"],
  "Kubernetes": ["K8s"],
  "Docker": ["Docker CE", "Docker EE"]
}
```

### Synonym Matching Logic

1. **Exact Match**: Direct skill name match
2. **Synonym Match**: Match against known synonyms
3. **Partial Match**: Fuzzy matching for close variations
4. **Suggestion**: Recommend similar skills for unmatched terms

## Frontend Integration

### Skill Selector Component

```javascript
// Skill search and selection component
const SkillSelector = ({ onSkillSelect, selectedSkills = [] }) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [suggestions, setSuggestions] = useState([]);

  const searchSkills = async (query) => {
    if (query.length < 2) return;

    const response = await fetch(
      `/api/skills/search/?q=${encodeURIComponent(query)}`
    );
    const results = await response.json();
    setSuggestions(results);
  };

  useEffect(() => {
    const timeoutId = setTimeout(() => searchSkills(searchTerm), 300);
    return () => clearTimeout(timeoutId);
  }, [searchTerm]);

  return (
    <div className="skill-selector">
      <input
        type="text"
        placeholder="Search skills..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      <div className="suggestions">
        {suggestions.map((skill) => (
          <SkillSuggestion
            key={skill.id}
            skill={skill}
            onSelect={() => onSkillSelect(skill)}
            isSelected={selectedSkills.includes(skill.id)}
          />
        ))}
      </div>
    </div>
  );
};
```

### Skill Categories Browser

```javascript
// Browse skills by category
const SkillBrowser = ({ onSkillSelect }) => {
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [categorySkills, setCategorySkills] = useState([]);

  const loadCategories = async () => {
    const response = await fetch("/api/skills/categories/");
    setCategories(await response.json());
  };

  const loadCategorySkills = async (categoryId) => {
    const response = await fetch(`/api/skills/category/${categoryId}/`);
    setCategorySkills(await response.json());
  };

  return (
    <div className="skill-browser">
      <div className="categories">
        {categories.map((category) => (
          <CategoryCard
            key={category.id}
            category={category}
            onClick={() => {
              setSelectedCategory(category);
              loadCategorySkills(category.id);
            }}
          />
        ))}
      </div>

      {selectedCategory && (
        <div className="category-skills">
          <h3>{selectedCategory.name}</h3>
          <div className="skills-grid">
            {categorySkills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                onSelect={() => onSkillSelect(skill)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

## Data Management

### Skill Standardization

```python
# Example skill normalization
def normalize_skill_name(name):
    """Normalize skill names for consistency"""
    # Remove extra whitespace
    name = ' '.join(name.split())

    # Handle common patterns
    replacements = {
        'javascript': 'JavaScript',
        'react.js': 'React',
        'node.js': 'Node.js',
        'postgresql': 'PostgreSQL'
    }

    return replacements.get(name.lower(), name)
```

### Bulk Import Support

```python
# Admin action for bulk skill import
def bulk_import_skills(modeladmin, request, queryset):
    """Import skills from CSV file"""
    # Implementation for importing skills from structured data
    pass
```

## Performance Considerations

### Database Optimization

- **Indexes**: Name fields indexed for fast searching
- **Category Ordering**: Skills ordered by category then name
- **Search Optimization**: Full-text search on names and synonyms
- **Caching**: Frequently accessed skills cached

### API Optimization

- **Pagination**: Large skill lists properly paginated
- **Filtering**: Category and search filtering
- **Lightweight Responses**: Minimal data for search/browse endpoints
- **Caching Headers**: Appropriate cache headers for static data

## Future Enhancements

### Advanced Features

1. **Skill Relationships**: Parent/child skill hierarchies
2. **Trending Skills**: Track popular/emerging skills
3. **Skill Levels**: Standardized proficiency definitions
4. **Certification Mapping**: Link skills to certifications
5. **Market Data**: Salary data and demand metrics

### AI Integration

1. **Skill Extraction**: Extract skills from job descriptions/resumes
2. **Skill Suggestions**: ML-powered skill recommendations
3. **Semantic Matching**: Advanced skill similarity detection
4. **Gap Analysis**: Identify skill gaps between candidates and jobs

### Analytics

1. **Skill Demand**: Track which skills are most requested
2. **Skill Growth**: Monitor emerging skill trends
3. **Matching Success**: Track skill-based matching effectiveness
4. **Market Intelligence**: Industry skill requirement analysis

This skills system provides the foundational taxonomy that enables intelligent matching throughout the entire job board
platform.
