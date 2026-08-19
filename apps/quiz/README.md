# Quiz App Documentation

## 1. Header & Overview

**Quiz App** - Career guidance and skills assessment platform for WorkXplorer

This app provides a comprehensive quiz system for career guidance and skill assessments. It manages quiz types, quizzes,
questions, answers, career options, and calculates personalized career recommendations based on user responses.

## 2. Features

- Multi-language support for all content (Uzbek, Russian, English)
- Hierarchical quiz structure (QuizType → Quiz → Question → AnswerChoice)
- Point-based scoring system linked to career options
- Automated career recommendation calculation with percentages
- Quiz result persistence for candidate tracking
- Active/inactive status for content management
- Admin interface with inline answer editing
- Optimized queries with prefetch_related to prevent N+1 issues

## 3. API Endpoints

### Public Endpoints

#### List Quiz Types

```
GET /api/quiz/types/
```

**Authentication**: None

**Query Parameters**:

- `id` (int, optional): Filter by specific quiz type ID

**Response**:

```json
{
  "success": true,
  "message": "Quiz types retrieved",
  "data": {
    "results": [
      {
        "id": 1,
        "name": "Career Guidance",
        "description": "Find your ideal career path",
        "is_active": true,
        "created_at": "2025-10-08T10:00:00Z"
      }
    ]
  }
}
```

**Features**:

- Returns only active quiz types
- No pagination
- Multi-language field support

---

#### List Quizzes

```
GET /api/quiz/list/
```

**Authentication**: None

**Query Parameters**:

- `quiz_type_id` (int, optional): Filter by quiz type

**Response**:

```json
[
  {
    "id": 1,
    "name": "Main Career Quiz",
    "description": "Discover your strengths",
    "quiz_type": {
      "id": 1,
      "name": "Career Guidance",
      "description": "...",
      "is_active": true,
      "created_at": "2025-10-08T10:00:00Z"
    },
    "question_count": 15,
    "is_active": true,
    "created_at": "2025-10-08T11:00:00Z"
  }
]
```

**Features**:

- Includes question count for active questions
- Nested quiz type details
- No pagination
- Optimized with select_related

---

#### Get Quiz Details

```
GET /api/quiz/<int:id>/
```

**Authentication**: None

**Response**:

```json
{
  "id": 1,
  "name": "Main Career Quiz",
  "description": "Discover your strengths",
  "quiz_type": {
    "id": 1,
    "name": "Career Guidance"
  },
  "questions": [
    {
      "id": 1,
      "title": "What activities do you enjoy?",
      "answers": [
        {
          "id": 10,
          "text": "Writing code",
          "point": 80
        },
        {
          "id": 11,
          "text": "Managing teams",
          "point": 60
        }
      ]
    }
  ],
  "is_active": true,
  "created_at": "2025-10-08T11:00:00Z"
}
```

**Features**:

- Includes all questions and answers
- Prefetched related data for performance
- Points visible to users

---

#### List Questions (Legacy)

```
GET /api/quiz/questions/
```

**Authentication**: None
**Status**: Deprecated - use quiz detail endpoint instead

**Query Parameters**:

- `quiz_id` (int, optional): Filter by quiz

**Response**:

```json
{
  "success": true,
  "message": "Questions retrieved",
  "data": {
    "results": [
      {
        "id": 1,
        "title": "What is Python?",
        "answers": [{ "id": 10, "text": "A programming language", "point": 80 }]
      }
    ]
  }
}
```

**Features**:

- Returns only active questions
- Legacy endpoint for backward compatibility

---

### Authenticated Endpoints

#### Calculate Quiz Result

```
POST /api/quiz/responses/
```

**Authentication**: Required (Candidate only)

**Request**:

```json
{
  "quiz_id": 1,
  "responses": [
    {
      "question_id": 1,
      "answer": [10, 11]
    },
    {
      "question_id": 2,
      "answer": [15]
    }
  ]
}
```

**Response**:

```json
{
  "results": [
    {
      "position": "Software Engineer",
      "score": 160,
      "percentage": "65%"
    },
    {
      "position": "Data Scientist",
      "score": 85,
      "percentage": "35%"
    }
  ]
}
```

**Features**:

- Validates quiz existence and active status
- Supports multiple answers per question
- Rejects question/answer pairs that do not belong to the submitted quiz
- Calculates percentage based on total score
- Saves top 3 career recommendations to database
- Returns career titles in request language
- Single optimized database query for all answer choices

---

#### Determine Domain (Domain Discovery)

```
POST /api/quiz/determine-domain/
```

**Authentication**: None (Public)

**Description**: 
This endpoint is used in a two-phase quiz process. First, candidates answer domain-discovery questions (typically quiz_id=1). Based on their answers, the system determines which domain (field/industry) best matches their interests. It then returns questions from quiz types associated with that domain for the second phase.

**Request**:

```json
{
  "quiz_id": 1,
  "responses": [
    {
      "question_id": 1,
      "answer_id": 10
    },
    {
      "question_id": 2,
      "answer_id": 22
    }
  ]
}
```

**Response**:

```json
{
  "determined_domain": {
    "id": 1,
    "name": "IT",
    "description": "Information Technology",
    "score": 25,
    "percentage": "60%"
  },
  "all_domain_scores": [
    {
      "domain_id": 1,
      "domain_name": "IT",
      "score": 25,
      "percentage": "60%"
    },
    {
      "domain_id": 2,
      "domain_name": "Healthcare",
      "score": 17,
      "percentage": "40%"
    }
  ],
  "questions": [
    {
      "id": 11,
      "title": "What programming language interests you?",
      "answers": [
        {"id": 101, "text": "Python", "point": 10},
        {"id": 102, "text": "JavaScript", "point": 10}
      ]
    }
  ]
}
```

**Features**:

- Calculates domain scores based on answer->domain mappings
- Returns the winning domain with highest score
- Returns all scored domains for transparency
- Rejects mismatched question/answer pairs from other quizzes
- Fetches questions from quiz types linked to the determined domain
- Optimized queries with select_related and prefetch_related
- Multi-language support (uz, ru, en)

---

## 4. Models

### QuizType

Categorizes quizzes into different types.

**Fields**:

- `name`: CharField(max_length=100) - Type identifier (e.g., "Career Guidance")
- `description`: TextField - Purpose explanation
- `domain`: ForeignKey to Domain (nullable) - Associated domain/field
- `is_active`: BooleanField(default=True) - Visibility control
- `created_at`, `updated_at`: Timestamps

**Features**:

- Multi-language fields (name, description)
- Soft-delete via is_active
- Orders by newest first
- Can be linked to a specific domain for domain-based filtering

**Use Cases**:

- Grouping related quizzes
- Filtering quizzes by category
- Domain-specific quiz categorization
- Admin organization

---

### Quiz

Individual quiz instances within a type.

**Fields**:

- `name`: CharField(max_length=255) - Quiz title
- `quiz_type`: ForeignKey to QuizType - Category classification
- `description`: TextField - Instructions/overview
- `is_active`: BooleanField(default=True) - Publication status
- `created_at`, `updated_at`: Timestamps

**Relationships**:

- `questions`: Reverse relation to Question
- `results`: Reverse relation to QuizResult

**Features**:

- Multi-language fields (name, description)
- Prefetch optimization for questions
- Cascades delete to questions

**Use Cases**:

- Main career guidance quiz
- Skill assessment tests
- Personality evaluations

---

### Question

Quiz questions with multiple answer choices.

**Fields**:

- `quiz`: ForeignKey to Quiz (nullable) - Parent quiz
- `title`: CharField(max_length=255) - Question text
- `is_active`: BooleanField(default=True) - Visibility toggle
- `created_at`, `updated_at`: Timestamps

**Relationships**:

- `answers`: Reverse relation to AnswerChoice

**Features**:

- Multi-language title field
- Nullable quiz for flexibility
- Orders by ID

**Use Cases**:

- Career preference questions
- Skill assessment items
- Interest evaluation prompts

---

### AnswerChoice

Possible answers to questions with scoring and domain mapping.

**Fields**:

- `question`: ForeignKey to Question - Parent question
- `text`: CharField(max_length=500) - Answer text
- `point`: SmallIntegerField (0-100) - Score value
- `career_option`: ForeignKey to CareerOption (nullable) - Links to career
- `domain`: ForeignKey to Domain (nullable) - Domain association for domain determination
- `created_at`, `updated_at`: Timestamps

**Validation**:

- Points: 0-100 range enforced by validators

**Features**:

- Multi-language text field
- Each answer contributes to specific career score
- Domain mapping for domain-discovery questions
- Cascades delete with question

**Use Cases**:

- Multiple choice answers
- Scoring different career paths
- Weighted preference options
- Domain determination in first quiz phase

---

### CareerOption

Career paths that can be recommended.

**Fields**:

- `title`: CharField(max_length=240) - Career name
- `description`: TextField(max_length=5000) - Career details
- `created_at`, `updated_at`: Timestamps

**Relationships**:

- `answer_choices`: Reverse relation to AnswerChoice

**Features**:

- Multi-language fields (title, description)
- Can be linked to multiple answers
- Independent entity (no foreign keys)

**Use Cases**:

- Software Engineer career path
- Data Scientist recommendations
- Manager positions

---

### QuizResult

Stores completed quiz results for candidates.

**Fields**:

- `candidate`: ForeignKey to Candidate - User who took quiz
- `quiz`: ForeignKey to Quiz (nullable) - Quiz taken
- `career_options`: JSONField(default=list) - Top 3 recommended careers
- `created_at`, `updated_at`: Timestamps

**Features**:

- Stores only top 3 career titles (space-efficient)
- Cascades delete with candidate
- Orders by newest first

**Use Cases**:

- Tracking candidate quiz history
- Displaying past recommendations
- Analytics on career interests

## 5. Business Logic

### Quiz Result Calculation Algorithm

**Input Processing**:

```python
# Request: {quiz_id: 1, responses: [{question_id: 1, answer: [10, 11]}]}
# Extract all answer IDs and question-answer pairs
answer_ids = [10, 11, 15, ...]
question_answer_pairs = [(1, 10), (1, 11), (2, 15), ...]
```

**Single Query Optimization**:

```python
# Fetch all needed data in one query
answer_choices = AnswerChoice.objects.select_related('career_option').filter(
    id__in=answer_ids,
    question__quiz=quiz
).values(
    'id', 'question_id', 'point',
    'career_option__title_en',
    'career_option__title_uz',
    'career_option__title_ru'
)
```

**Score Calculation**:

```python
# Build lookup dictionary
answer_lookup = {(question_id, answer_id): {'point': x, 'career_title': y}}

# Calculate scores per career
score_map = defaultdict(int)
for question_id, answer_id in question_answer_pairs:
    answer_data = answer_lookup.get((question_id, answer_id))
    if answer_data:
        score_map[answer_data['career_title']] += answer_data['point']

# Example: {'Software Engineer': 160, 'Data Scientist': 85}
```

**Percentage Calculation**:

```python
total_score = sum(score_map.values())  # 245
percentage = round((160 / 245) * 100)  # 65%
```

**Language-Aware Career Titles**:

```python
# Select title based on Accept-Language header
if lang == 'uz':
    title = career_option__title_uz or career_option__title_en
elif lang == 'ru':
    title = career_option__title_ru or career_option__title_en
else:
    title = career_option__title_en or career_option__title
```

### Admin Inline Editing

**AnswerChoiceInline Configuration**:

- Allows adding/editing answers within question form
- `extra=1`: Shows one empty answer form
- `min_num=1`: Requires at least one answer
- `show_change_link=True`: Direct editing link

**Benefits**:

- Faster quiz creation workflow
- Visual question-answer relationship
- Immediate validation feedback

## 6. Multi-Language Support

**Supported Languages**: uz (Uzbek), ru (Russian), en (English)

**Translated Models**:

- QuizType: name, description
- Quiz: name, description
- Question: title
- AnswerChoice: text
- CareerOption: title, description

**Implementation**: django-modeltranslation

- Creates separate columns (e.g., `title_en`, `title_uz`, `title_ru`)
- Automatically serves correct language based on request
- Fallback to English if translation missing

**Language Selection**:

```python
# In calculate_quiz view
lang = translation.get_language() or 'en'
# Returns career titles in user's language
```

## 7. Error Responses

### 400 Bad Request

**Missing quiz_id**:

```json
{ "error": "quiz_id is required" }
```

**Empty responses**:

```json
{ "error": "Responses are required" }
```

**Invalid answers**:

```json
{ "error": "No valid answers provided" }
```

**No valid answers for quiz**:

```json
{ "error": "No valid answers provided for this quiz" }
```

### 401 Unauthorized

```json
{ "detail": "Authentication credentials were not provided." }
```

### 404 Not Found

**Quiz not found**:

```json
{ "error": "Quiz not found" }
```

**Quiz detail endpoint**:

```json
{ "detail": "Not found." }
```

## 8. Security

**Permission Classes**:

- Quiz listing/detail: AllowAny (public access)
- Calculate result: IsAuthenticated + IsCandidatePermission

**Data Validation**:

- Point values: 0-100 range enforced
- Answer IDs validated against database
- Quiz existence and active status verified
- Question-answer-quiz relationship validated

**Role Restrictions**:

- Only candidates can submit quiz responses
- Recruiters cannot take quizzes

**Input Sanitization**:

- All user input validated before processing
- Invalid answer IDs filtered out
- Question IDs verified

## 9. Testing

### Run Tests

```bash
python manage.py test apps.quiz
python manage.py test apps.quiz.tests.test_models
python manage.py test apps.quiz.tests.test_views
```

### Model Test Coverage

- QuizType creation and string representation
- Quiz relationship with QuizType
- Question with/without quiz
- AnswerChoice point validation
- CareerOption with empty description
- QuizResult relationship with candidate
- Default values and is_active toggles

### View Test Coverage

- Question list returns only active questions
- Question list excludes inactive questions
- Calculate result requires authentication
- Calculate result validates responses
- Invalid answer IDs return 400
- Empty responses return 400
- Response structure validation

## 10. Admin Interface

### QuestionAdmin

- **List display**: ID, title, created_at, updated_at
- **Search**: Question text
- **Inline**: AnswerChoiceInline for managing answers
- **Feature**: Add/edit answers within question form

### AnswerChoiceAdmin

- **List display**: ID, question, text, point, timestamps
- **Search**: Answer text
- **Feature**: Direct answer management

### CareerOptionAdmin

- **List display**: ID, title, created_at, updated_at
- **Search**: Title, description
- **Ordering**: Newest first

### QuizResultAdmin

- **List display**: ID, candidate, created_at
- **Search**: Candidate email
- **Ordering**: Newest first
- **Feature**: View candidate quiz history

### QuizType and Quiz

- Basic registration with standard CRUD
- Support for multi-language fields

## 11. Performance

### Current Optimizations

- `select_related('quiz_type')` for quiz listings
- `prefetch_related('questions__answers')` for quiz details
- Single query for all answer choices in calculation
- Dictionary lookup for O(1) answer retrieval
- No pagination on small datasets (quiz types, lists)

### Query Patterns

```python
# Quiz list: 2 queries (quiz + quiz_type)
Quiz.objects.filter(is_active=True).select_related('quiz_type')

# Quiz detail: 3 queries (quiz + questions + answers)
Quiz.objects.filter(id=x).prefetch_related('questions__answers', 'quiz_type')

# Calculate result: 1 query for all answers
AnswerChoice.objects.select_related('career_option').filter(
    id__in=answer_ids
).values(...)
```

### Recommendations

**Caching Quiz Content**:

```python
from django.core.cache import cache

def get_quiz_cached(quiz_id):
    cache_key = f'quiz_detail:{quiz_id}'
    quiz = cache.get(cache_key)
    if not quiz:
        quiz = Quiz.objects.prefetch_related(...).get(id=quiz_id)
        cache.set(cache_key, quiz, 3600)
    return quiz
```

**Database Indexes**:

```python
# Add indexes for common queries
class Meta:
    indexes = [
        models.Index(fields=['quiz', 'is_active']),  # Question filtering
        models.Index(fields=['quiz_type', 'is_active']),  # Quiz filtering
    ]
```

## 12. Integration Points

### Used By Other Apps

- Authentication app: Candidate model for quiz results
- May integrate with profiles app for career recommendations

### Provides Services

- Career recommendation engine
- Quiz taking functionality
- Result tracking for candidates

### Dependencies

- **django-modeltranslation**: Multi-language support
- **djangorestframework**: API serialization
- **drf-spectacular**: API documentation
- **django-filter**: Query parameter filtering

---

## Tutorial: Understanding the Quiz System

### How Quiz Structure Works

**Hierarchy**:

```
QuizType (Career Guidance)
  └── Quiz (Main Career Quiz)
        └── Question (What activities do you enjoy?)
              ├── Answer 1 (Writing code) → Software Engineer [80 points]
              ├── Answer 2 (Managing teams) → Manager [60 points]
              └── Answer 3 (Analyzing data) → Data Scientist [70 points]
```

### Creating a Quiz (Admin Flow)

**Step 1**: Create QuizType

```
Name: "Career Guidance"
Description: "Find your ideal career"
```

**Step 2**: Create Quiz

```
Name: "Technology Career Quiz"
Quiz Type: Career Guidance
```

**Step 3**: Create Question

```
Title: "What do you prefer?"
Quiz: Technology Career Quiz
```

**Step 4**: Add Answers (inline)

```
Answer 1: "Building websites" → 80 points → Frontend Developer
Answer 2: "Database design" → 70 points → Backend Developer
Answer 3: "Mobile apps" → 75 points → Mobile Developer
```

### How Scoring Works

When a candidate selects answers:

1. Each answer has points (0-100)
2. Points accumulate for the linked career option
3. Final scores converted to percentages
4. Top careers ranked and saved

**Example**:

```
Question 1: Answer A (Software Engineer: +80)
Question 2: Answer B (Software Engineer: +70)
Question 3: Answer C (Data Scientist: +60)

Total: Software Engineer = 150, Data Scientist = 60
Percentages: 71% Software Engineer, 29% Data Scientist
```

This creates personalized recommendations based on user preferences rather than simple keyword matching.
