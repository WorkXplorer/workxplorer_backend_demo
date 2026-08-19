# Matching App Documentation

## 1. Header & Overview

**Matching App** - AI-powered semantic matching engine for WorkXplorer

This app provides intelligent matching between resumes and vacancies using vector embeddings and cosine similarity. It translates multi-language content, generates semantic embeddings, and finds the best matches based on meaning rather than keywords.

## 2. Features

- Semantic matching using sentence-transformer embeddings (384 dimensions)
- Multi-language support with automatic translation to English
- ONNX-optimized model for 2-4x faster inference
- Cosine similarity scoring with configurable thresholds
- Batch translation with concurrent processing
- Language detection with confidence scoring
- Match quality ratings (Excellent/Very Good/Good/Fair/Poor)
- Singleton model pattern for optimal memory usage

## 3. API Endpoints

### Authenticated Endpoints

#### Match Resume to Vacancies

```
GET /api/matching/resume/<uuid:resume_id>/vacancies/
```

**Authentication**: Required

**Query Parameters**:

- `top_k` (int, optional): Number of results (default: 20, max: 50)
- `min_similarity` (float, optional): Minimum score 0-1 (default: 0.5)

**Response**:

```json
{
  "resume_id": "550e8400-e29b-41d4-a716-446655440000",
  "resume_title": "Senior Python Developer Resume",
  "matches_found": 3,
  "matches": [
    {
      "vacancy": {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "title": "Python Backend Developer",
        "company": { "name": "TechCorp" }
      },
      "similarity_score": 0.872,
      "match_percentage": 87.2,
      "match_quality": "Excellent"
    }
  ]
}
```

**Features**:

- Returns only active vacancies with embeddings
- Results sorted by similarity (highest first)
- Filters by min_similarity threshold
- Limited by top_k parameter

---

#### Match Vacancy to Resumes

```
GET /api/matching/vacancy/<uuid:vacancy_id>/resumes/
```

**Authentication**: Required

**Query Parameters**:

- `top_k` (int, optional): Number of results (default: 20, max: 50)
- `min_similarity` (float, optional): Minimum score 0-1 (default: 0.5)

**Response**:

```json
{
  "vacancy_id": "660e8400-e29b-41d4-a716-446655440001",
  "vacancy_title": "Senior Backend Developer",
  "company_name": "TechCorp",
  "matches_found": 5,
  "matches": [
    {
      "resume": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Python Developer Resume",
        "candidate": { "email": "candidate@example.com" }
      },
      "similarity_score": 0.853,
      "match_percentage": 85.3,
      "match_quality": "Excellent"
    }
  ]
}
```

**Features**:

- Finds candidates for specific vacancy
- Only matches resumes with embeddings
- Configurable similarity threshold
- Ranked by match quality

## 4. Models

This app has no database models. It operates on embeddings stored in Resume and Vacancy models from other apps.

**Required Fields on External Models**:

- `embedding`: ArrayField (384 floats) - Vector representation
- `is_embedded`: BooleanField - Whether embedding exists
- `combined_text_en`: TextField - English text used for embedding

## 5. Business Logic

### Embedding Generation Pipeline

**Step 1: Text Extraction**

```python
# Resume/Vacancy models provide get_text_for_embedding()
text = vacancy.get_text_for_embedding()
# Combines: title, description, requirements, benefits, etc.
```

**Step 2: Translation**

```python
# Detect language with confidence
needs_translation, lang, confidence = detect_language_and_confidence(text)

# Translate if needed (saves API calls for English text)
if needs_translation:
    translated = GoogleTranslator(source="auto", target="en").translate(text)
```

**Step 3: Vectorization**

```python
# Tokenize text
inputs = tokenizer(text, padding=True, truncation=True, max_length=512)

# Generate embedding with mean pooling
outputs = model(**inputs)
embeddings = mean_pool(outputs.last_hidden_state, attention_mask)

# Normalize to unit length for cosine similarity
embeddings = F.normalize(embeddings, p=2, dim=1)
```

**Step 4: Storage**

```python
vacancy.combined_text_en = translated_text
vacancy.embedding = embedding.tolist()  # Convert numpy to list
vacancy.is_embedded = True
vacancy.save()
```

### Matching Algorithm

**Cosine Distance Formula**:

```python
# pgvector calculates distance: 0 (identical) to 2 (opposite)
distance = CosineDistance("embedding", target_embedding)

# Convert to similarity: 0 (no match) to 1 (perfect match)
similarity = 1 - distance
```

**Query Pattern**:

```python
Resume.objects.annotate(
    distance=CosineDistance("embedding", vacancy.embedding)
).filter(
    embedding__isnull=False,
    is_embedded=True
).order_by("distance")[:top_k]
```

### ONNX Model Optimization

**Singleton Pattern**:

```python
# Model loaded once at startup, reused for all requests
_tokenizer = None
_model = None

def get_embedding_model():
    global _tokenizer, _model
    if _tokenizer is None:
        _tokenizer, _model = setup_onnx_model()
    return _tokenizer, _model
```

**ONNX Benefits**:

- 2-4x faster inference than PyTorch
- 50% smaller memory footprint
- Optimized for CPU inference
- First run converts model (slow), subsequent runs use cache

**Mean Pooling Strategy**:

```python
# Average all token embeddings, weighted by attention mask
token_embeddings * attention_mask  # Mask padding tokens
sum(embeddings) / sum(attention_mask)  # Average
```

### Translation Strategies

**Synchronous (Single Text)**:

- Used in API endpoints for real-time processing
- Skips translation if confidence >= 0.8 that text is English
- Returns original text on translation failure

**Asynchronous (Batch)**:

- Used for bulk processing multiple texts
- Concurrent translations with semaphore (max 5 concurrent)
- Language analysis before translation to skip unnecessary calls

**Language Detection**:

```python
# Returns list of (language, confidence) tuples
langs = detect_langs(text)
# Example: [('en', 0.92), ('es', 0.06), ...]

# Find English confidence
english_confidence = next((l.prob for l in langs if l.lang == 'en'), 0.0)

# Translate if confidence < 0.8
needs_translation = english_confidence < 0.8
```

## 6. Multi-Language Support

**Supported Input Languages**: Any language supported by Google Translate (Uzbek, Russian, English, etc.)

**Translation Flow**:

- Detects source language automatically
- Confidence threshold: 0.8 (80% certain it's English)
- Short texts (<10 chars) always translated
- Failed detection defaults to translation

**Why English Only for Embeddings**:

- Model trained primarily on English corpus
- Better semantic understanding in English
- Consistent comparison space for all languages

## 7. Error Responses

### 400 Bad Request

**Missing Embedding**:

```json
{
  "error": "Resume embedding not generated yet",
  "message": "Please wait a moment and try again. Embeddings are being processed."
}
```

**Invalid Similarity Range**:

```json
{
  "error": "min_similarity must be between 0 and 1"
}
```

### 401 Unauthorized

```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 404 Not Found

```json
{
  "detail": "Not found."
}
```

### 500 Internal Server Error

```json
{
  "error": "Matching failed: Invalid embedding dimensions"
}
```

## 8. Security

**Authentication**:

- All endpoints require IsAuthenticated
- No role-based restrictions (candidates and recruiters can both match)

**Data Access**:

- Users can match any resume/vacancy with valid ID
- No ownership validation (consider adding for production)

**Rate Limiting**:

- Should be implemented at application level
- Vector operations are CPU-intensive

**Input Validation**:

- top_k capped at 50 to prevent resource exhaustion
- min_similarity validated to 0-1 range
- UUID validation via Django URL patterns

## 9. Testing

### Run Tests

```bash
python manage.py test apps.matching
coverage run --source='apps.matching' manage.py test apps.matching
```

### Coverage

- Resume to vacancies matching with valid embeddings
- Vacancy to resumes matching with authentication
- Missing embedding error handling
- Custom parameter validation (top_k, min_similarity)
- Authentication requirement enforcement
- Match quality rating assignment

### Test Data

- Uses random numpy embeddings for isolation
- No dependency on actual ML model during tests
- Tests API contract, not embedding quality

## 10. Admin Interface

No admin interface registered. This app has no models.

**Management via**:

- Django shell for testing services
- Custom management commands for bulk embedding generation

## 11. Performance

### Current Optimizations

- ONNX model reduces inference time by 2-4x
- Singleton pattern prevents repeated model loading
- Batch processing for multiple texts (concurrent translation)
- pgvector native cosine distance (optimized in C)
- Mean pooling reduces embedding computation

### Model Specifications

- Model: sentence-transformers/all-MiniLM-L6-v2
- Embedding size: 384 dimensions
- Max token length: 512 tokens
- Memory per model instance: ~90MB

### Recommendations

**Caching Embeddings**:

```python
# Already implemented - embeddings stored in database
# No recalculation on each match request
```

**Async Translation**:

```python
# For bulk operations, use translation_batched.py
texts = [v.get_text_for_embedding() for v in vacancies]
translated = await translate_texts_batch(texts, max_concurrent=5)
```

**GPU Acceleration**:

```python
# For high-volume processing, consider GPU deployment
# ONNX supports both CPU and GPU backends
model = ORTModelForFeatureExtraction.from_pretrained(
    model_name,
    provider="CUDAExecutionProvider"  # GPU
)
```

**Batch Matching**:

```python
# Match multiple resumes at once
embeddings_batch = encode_texts_batch([r.combined_text_en for r in resumes])
# More efficient than individual encode_text() calls
```

## 12. Integration Points

### Used By Other Apps

- Vacancies app: generates embeddings when vacancy created/updated
- Resumes app: generates embeddings when resume created/updated
- Both apps call EmbeddingGenerator.generate_for_vacancy/resume()

### Depends On

- **pgvector**: PostgreSQL extension for vector operations
- **sentence-transformers**: Pre-trained embedding model
- **deep-translator**: Google Translate API wrapper
- **langdetect**: Language identification
- **optimum**: ONNX runtime optimization

### External APIs

- Google Translate API (via deep-translator library)
- HuggingFace model hub (model download, first time only)

### Database Requirements

```sql
-- PostgreSQL with pgvector extension
CREATE EXTENSION vector;

-- Embedding column on Resume/Vacancy models
ALTER TABLE resumes ADD COLUMN embedding vector(384);
CREATE INDEX ON resumes USING ivfflat (embedding vector_cosine_ops);
```

---

## Tutorial: How Semantic Matching Works

### Understanding Vector Embeddings

**What is an embedding?**
An embedding converts text into a list of 384 numbers that capture semantic meaning. Similar meanings have similar numbers.

```python
# Example embeddings (simplified)
"Python developer" → [0.8, 0.1, 0.3, ...]
"Python programmer" → [0.79, 0.12, 0.31, ...]  # Very similar!
"Chef" → [0.1, 0.9, 0.05, ...]  # Very different!
```

### How Matching Finds Similar Jobs

**Step 1**: Convert your resume to numbers (embedding)

```python
resume_text = "5 years Python, Django, REST APIs"
resume_embedding = encode_text(resume_text)  # [0.8, 0.1, ...]
```

**Step 2**: Compare to all vacancy embeddings in database

```python
# Database calculates distance between vectors
distance = cosine_distance(resume_embedding, vacancy_embedding)
similarity = 1 - distance  # 0.85 = 85% match
```

**Step 3**: Return best matches sorted by similarity

### Why Translation to English?

The embedding model was trained mostly on English text, so it understands English better. We translate everything to English first for consistent, high-quality matches.

```python
# Uzbek text
"Python dasturchisi, 5 yillik tajriba"
    ↓ (translate)
"Python developer, 5 years experience"
    ↓ (encode)
[0.8, 0.1, 0.3, ...]  # Embedding
```

### Match Quality Ratings

- **0.8-1.0 (Excellent)**: Very strong match, highly recommended
- **0.7-0.8 (Very Good)**: Strong match, good candidate
- **0.6-0.7 (Good)**: Decent match, worth considering
- **0.5-0.6 (Fair)**: Weak match, some overlap
- **<0.5 (Poor)**: Very weak match, not recommended

This approach finds matches based on meaning, not just keyword matching. A "software engineer" resume can match "developer" vacancies even though the exact words differ.
