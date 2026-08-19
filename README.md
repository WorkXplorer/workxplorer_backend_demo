# WorkXplorer Backend Demo

This is a demo overview of the WorkXplorer backend, prepared for the President Tech Award admission.

The live MVP is available at **[app.workxplorer.uz](https://app.workxplorer.uz)**.

> Note: this repository contains the WorkXplorer Django backend, adapted for public sharing. The frontend and several supporting services are proprietary and live in a private repository (see "How to Launch" below).

## 🚀 Overview

WorkXplorer is a modern job board platform designed to help students find jobs, similar to HeadHunter (hh.uz). The platform connects candidates with recruiters through intelligent skill-based matching, comprehensive profile management, and a complete job application workflow from posting to hiring.

### Key Features for Students

- **Advanced Job Search**: Search and filter job postings by keywords, location, salary, employment type, and required skills
- **Smart Filtering**: Multiple filters can be combined to find the perfect job match
- **Real-time Updates**: See the latest job postings sorted by date or salary
- **Skill Matching**: Find jobs that match your skill set and experience level
- **Application Tracking**: Track all your job applications in one place
- **Resume Management**: Build and manage multiple versions of your resume
- **Direct Application**: Apply to jobs directly with your profile and resume

## 🏗️ Architecture

WorkXplorer is built on Django REST Framework with a modular component-based architecture.

### Tech Stack

- **Backend**: Django 5.x + Django REST Framework
- **Database**: PostgreSQL 15+ with pgvector extension (vector embeddings)
- **Cache/Queue**: Redis (cache + RQ background tasks)
- **AI**: AI-assisted resume generation, skill validation, and vacancy creation
- **Embeddings**: Internal embedding service for intelligent vacancy-resume matching
- **Auth**: Cookie-based JWT authentication (httpOnly cookies)
- **Push**: Firebase Cloud Messaging (FCM)

### Project Structure

```
apps/              # Django apps (authentication, profiles, vacancies,
                    #   resumes, applications, matching, ...)
config/
└── settings/       # Modular settings
core/               # Shared utilities (APIResponse, pagination, test runner)
utils/              # Abstract models, fields, upload validation, currency
```

## 🔍 Job Search Features

- **Text Search**: Search across job titles, descriptions, locations, and company names
- **Location**: Filter by work location (e.g., "Tashkent", "remote", "Samarkand")
- **Employment Type**: FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP
- **Salary Range**: Set minimum and maximum salary expectations
- **Skills**: Find jobs requiring specific skills
- **Sorting**: Newest first, highest/lowest salary, alphabetical by title

## 🛠️ How to Launch

This repository is the Django REST API by itself. WorkXplorer is a commercial project, so the **frontend and some supporting services live in a private repository** and are not published here — this backend alone won't give you the full product experience. To try the actual product, use the live MVP: **[app.workxplorer.uz](https://app.workxplorer.uz)**.

### Option A: Docker (recommended)

This spins up Postgres (with `pgvector` pre-installed), Redis, the API, and an RQ worker/scheduler — no local Python/Postgres setup needed.

```bash
cp .env.example .env.development
# edit .env.development — at minimum set SECRET_KEY and JWT_SECRET_KEY
docker compose -f docker-compose.dev.yml up --build
```

The API is now available at `http://localhost:8000/`. Run one-off management commands (migrations happen automatically via the container's entrypoint, but to create a superuser):

```bash
docker compose -f docker-compose.dev.yml exec workxplorer-backend python manage.py migrate
docker compose -f docker-compose.dev.yml exec workxplorer-backend python manage.py createsuperuser
```

The `chat` service in the compose file talks to a separate private repository (WORKXPLORER-CHAT) and is not required to run the backend — it's opt-in via `docker compose -f docker-compose.dev.yml --profile chat up`.

### Option B: Local Python

1. **Prerequisites**: Python 3.11+, PostgreSQL 15+ with the `pgvector` extension enabled, and Redis.

2. **Install dependencies**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env.development
   # edit .env.development with your local DB/Redis credentials and secrets
   ```

4. **Create the database** (with the pgvector extension)
   ```bash
   createdb workxplorer_demo
   psql -d workxplorer_demo -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```

5. **Run migrations and start the server**
   ```bash
   export DJANGO_ENVIRONMENT=development
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```

   The API is now available at `http://localhost:8000/`, e.g. `GET /api/v1/vacancies/`. Django admin lives at a non-default path (see `config/urls/base.py`).

6. **Background jobs** (optional, for AI-powered features, notifications, etc.)
   ```bash
   python manage.py rqworker default high low --with-scheduler
   ```

AI-powered features (resume generation, skill validation, evaluation) call out to a configurable AI provider and require the corresponding API credentials (see `.env.example`); without them they simply no-op. Firebase push notifications are optional and degrade gracefully without credentials.

## 🔒 What's different from the production codebase

This repo is adapted from the production backend for public sharing:
- Deployment scripts and production/staging Docker configs are excluded.
- The frontend and a few supporting services remain in a private repository.
