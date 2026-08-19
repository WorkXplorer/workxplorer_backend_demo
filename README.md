# WorkXplorer Backend Demo

This is a demo overview of the WorkXplorer backend, prepared for the President Tech Award admission.

The live MVP is available at **[app.workxplorer.uz](https://app.workxplorer.uz)**.

> Note: this repository is a high-level showcase, not the full production codebase. Several features and internal implementation details are not shown here because they are proprietary.

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

### Project Structure (production codebase)

```
workxplorer_backend/
├── apps/              # Django apps (authentication, profiles, vacancies,
│                      #   resumes, applications, matching, ...)
├── config/
│   └── settings/      # Modular settings
├── core/               # Shared utilities (APIResponse, pagination, test runner)
└── utils/              # Abstract models, fields, upload validation, currency
```

## 🔍 Job Search Features

- **Text Search**: Search across job titles, descriptions, locations, and company names
- **Location**: Filter by work location (e.g., "Tashkent", "remote", "Samarkand")
- **Employment Type**: FULL_TIME, PART_TIME, CONTRACT, INTERNSHIP
- **Salary Range**: Set minimum and maximum salary expectations
- **Skills**: Find jobs requiring specific skills
- **Sorting**: Newest first, highest/lowest salary, alphabetical by title

## 🛠️ How to Launch

WorkXplorer is a commercial project, so the frontend and the rest of the backing services are kept in a **private repository** and are not published here. This repo is a public-facing overview only.

The general shape of running the full platform (in the private repos) is:

1. **Backend (Django REST API)**
   - Requires Python 3.11+, PostgreSQL 15+ (with `pgvector`), and Redis.
   - Install dependencies: `pip install -r requirements.txt`
   - Configure environment variables (database, Redis, JWT secrets, AI provider keys, Firebase credentials).
   - Run migrations: `python manage.py migrate`
   - Start the API: `python manage.py runserver` (or via Gunicorn/Docker in production)
   - Background jobs run through RQ workers: `python manage.py rqworker default high low --with-scheduler`

2. **Frontend**
   - Lives in a separate private repository and consumes the backend REST API.
   - Not published here for commercial/IP reasons.

3. **Supporting services** (embeddings, notifications, etc.)
   - Also live in private repositories and are deployed alongside the backend.

To try the product itself without setting anything up locally, use the live MVP: **[app.workxplorer.uz](https://app.workxplorer.uz)**.

## 🔒 What's not included in this demo

Some parts of the platform are intentionally left out of this public repository, as they contain proprietary business logic and algorithms (e.g. matching/scoring internals, AI evaluation pipelines, and analytics). This repo focuses on giving reviewers a clear picture of the product without exposing that IP.
