# Authentication App

The Authentication app provides user management, registration, and JWT-based authentication with httpOnly cookies for secure session management across candidates and recruiters.

## Overview

This app implements a multi-user system with role-based access control, supporting two primary user types: Candidates (job seekers) and Recruiters (hiring managers). It uses JWT tokens stored in httpOnly cookies for enhanced security.

## Features

- **Multi-User System**: Separate user types with different capabilities
- **Secure Authentication**: JWT tokens with httpOnly cookies
- **Company Management**: Organization structure for recruiters
- **Role-Based Access**: Automatic permission handling based on user type
- **Token Management**: Automatic refresh and blacklisting

## User Types

### Candidates

- Job seekers who browse and apply to vacancies
- Can create profiles, upload resumes, and track applications
- Identified by `is_candidate=True` flag

### Recruiters

- Hiring managers who post vacancies and manage applications
- Must be associated with a Company
- Can review applications and update hiring pipeline status
- Identified by `is_recruiter=True` flag

### Companies

- Organizations that post job vacancies
- Have multiple recruiters
- Identified by name and TIN (Tax Identification Number)

## API Endpoints

### Authentication Endpoints

#### Login

```http
POST /auth/login/
```

**Purpose**: Authenticate user and set httpOnly cookies

**Authentication**: None required

**Request Body**:

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response** (200 OK):

```json
{
  "message": "Login successful",
  "user": {
    "email": "user@example.com"
  }
}
```

**Cookies Set**:

- `access_token`: JWT access token (15 minutes, httpOnly)
- `refresh_token`: JWT refresh token (7 days, httpOnly)

**Security Features**:

- Tokens stored in httpOnly cookies (not accessible via JavaScript)
- Secure flag in production
- SameSite=Strict for CSRF protection

---

#### Refresh Token

```http
POST /auth/refresh/
```

**Purpose**: Get new access token using refresh token from cookies

**Authentication**: None required (uses refresh_token cookie)

**Request Body**: Empty

**Response** (200 OK):

```json
{
  "message": "Token refreshed successfully"
}
```

**Behavior**:

- Reads refresh token from httpOnly cookie
- Issues new access token
- Optionally rotates refresh token (if enabled in settings)
- Updates cookies with new tokens

---

#### Token Verification

```http
POST /auth/verify/
```

**Purpose**: Verify if current access token is valid

**Authentication**: None required (uses access_token cookie)

**Response** (200 OK):

```json
{
  "message": "Token is valid"
}
```

**Use Cases**:

- Frontend route guards
- Session validation
- API health checks

---

#### Logout

```http
POST /auth/logout/
```

**Purpose**: Invalidate tokens and clear cookies

**Authentication**: Required

**Response** (200 OK):

```json
{
  "message": "Successfully logged out"
}
```

**Behavior**:

- Blacklists refresh token (prevents reuse)
- Clears both access_token and refresh_token cookies
- Works even if tokens are already invalid

---

### Mobile App Authentication

Full request/response contract, error codes, and the recommended client flow
are in **[docs/MOBILE_AUTH_API_GUIDE.md](../../../docs/MOBILE_AUTH_API_GUIDE.md)**
— that's the doc to hand the mobile team. Summary of what exists:

The React Native app cannot rely on httpOnly cookies, so it uses a separate
set of endpoints under `/auth/mobile/` that return tokens in the JSON
response body instead. Every request requires the `X-Mobile-App-Key` header
(`MOBILE_APP_API_KEY` setting; missing/wrong key → `403`, fails closed if
the setting itself is unset). Scope is candidate-only — a recruiter/
university account gets `WRONG_USER_TYPE`.

Unlike the web cookie flow (single rotating JWT refresh token), mobile uses
a proper session model: each device install gets its own `MobileSession`
row backed by an **opaque, HMAC-hashed refresh token** (never a JWT, never
stored raw). Refresh rotates the token on every call; presenting an
already-rotated-away token is treated as theft and revokes that device's
whole session. Access tokens carry a `sid` claim so `logout`/`logout-all`
take effect immediately (`CookieJWTAuthentication` checks it), not just at
the token's natural 15-minute expiry.

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /auth/mobile/login/` | mobile key | Email/phone + password, candidate-only |
| `POST /auth/mobile/oauth/challenge/` | mobile key | One-time nonce/state before native Google/Apple sign-in |
| `POST /auth/mobile/google/` | mobile key | Verify Google ID token, login/register |
| `POST /auth/mobile/apple/` | mobile key | Verify Apple identity token + code exchange, login/register (iOS only) |
| `POST /auth/mobile/refresh/` | mobile key | Rotate refresh token |
| `POST /auth/mobile/logout/` | mobile key | Revoke this device's session only |
| `POST /auth/mobile/logout-all/` | Bearer + mobile key | Revoke every device |

Session lifetime: `MOBILE_SESSION_IDLE_TTL_DAYS` (default 60, resets on
every refresh) and `MOBILE_SESSION_ABSOLUTE_TTL_DAYS` (default 180, fixed
from creation) — see Configuration below.

#### Checking the OAuth setup without a device

```bash
python manage.py check_mobile_oauth            # add --offline to skip the network probes
```

Run it on the box that serves `/auth/mobile/*`. It verifies the app gate,
the challenge TTL, Redis, the Google audience and certs endpoint, and — the
part worth having — the whole Apple credential chain: that the `.p8` loads
and signs an ES256 `client_secret`, that the Fernet key round-trips, and
that **Apple itself accepts the credentials**. That last check exchanges a
deliberately bogus code: Apple validates `client_id`/`client_secret` before
the code, so `invalid_grant` back means the credentials are right (only the
throwaway code was wrong) and `invalid_client` means `APPLE_TEAM_ID` /
`APPLE_KEY_ID` / `APPLE_CLIENT_ID` / the `.p8` don't agree. That is the
question an iOS device would otherwise have to answer.

Nothing operator-side returns a `500` any more: a missing or unusable Apple
secret is `503 APPLE_NOT_CONFIGURED`, an unreachable provider is `503
APPLE_UNAVAILABLE` / `GOOGLE_UNAVAILABLE`, and a rejected challenge logs
which check failed (`device_id_mismatch`, `already_consumed`,
`nonce_mismatch`, …) while still returning the opaque
`OAUTH_CHALLENGE_INVALID` to the client.

---

### Phone Verification & Phone Login

Any authenticated user (candidate or recruiter, web or mobile — both
authenticate via the same `CookieJWTAuthentication`, cookie or Bearer header)
can verify a phone number and then use it as an alternate login identifier.

#### Send Phone OTP

```http
POST /auth/phone/send-otp/
```

**Purpose**: Send a one-time code to the authenticated user's phone via Eskiz.uz

**Authentication**: Required

**Request Body**:

```json
{ "phone": "+998901234567" }
```

**Behavior**:

- Accepts any reasonable Uzbek phone format and normalizes to `+998XXXXXXXXX`.
- Rate-limited: `OTP_RESEND_COOLDOWN_SECONDS` between sends, `OTP_MAX_SENDS_PER_DAY`
  per number per day (`429` when exceeded).
- `409` if the phone is already verified on a different account.

---

#### Verify Phone OTP

```http
POST /auth/phone/verify-otp/
```

**Purpose**: Confirm the code and attach the phone number to the authenticated user

**Authentication**: Required

**Request Body**:

```json
{ "phone": "+998901234567", "code": "123456" }
```

**Behavior**:

- Up to `OTP_MAX_VERIFY_ATTEMPTS` wrong guesses per code before it's invalidated
  (`429`, requires requesting a new code).
- On success, sets `phone` + `phone_verified_at` on the user — from then on,
  `/auth/login/` and `/auth/mobile/login/` accept `phone` in place of `email`
  (same password). Resolution happens in `EmailOrPhoneBackend`
  (`apps/authentication/backends.py`) — a custom Django authentication
  backend, not per-view logic, so every `authenticate()` caller gets both
  for free. It's also timing-safe: an unknown/unverified identifier runs the
  same password-hash cost as a real check, so response latency can't be used
  to enumerate registered phones/emails.

#### Phone Registration (no existing account)

```http
POST /auth/phone/register/send-otp/     { "phone": "+998901234567" }
POST /auth/phone/register/verify/       { "phone", "code", "email", "password" }
```

Unauthenticated — this is signup, not verification of an existing account.
`verify` creates an already-phone-verified Candidate in one step (no
set-password email, unlike the existing email-only
`POST /users/register/candidate/` flow) and returns `201`. Still requires
`email`: `CustomUser.email` is a required, unique field used throughout the
platform, so this adds phone as a *second* verified login identifier rather
than replacing email — pure phone-only (no email) accounts would need a
separate, larger migration.

---

### Registration Endpoints

#### Register Candidate

```http
POST /api/auth/register/candidate/
```

**Purpose**: Create new candidate account

**Authentication**: None required

**Request Body**:

```json
{
  "email": "candidate@example.com",
  "password": "securepassword123"
}
```

**Response** (201 Created):

```json
{
  "email": "candidate@example.com",
  "is_candidate": true
}
```

**Automatic Behavior**:

- Sets `is_candidate=True`
- Sets `is_active=True`
- Hashes password securely

---

#### Register Recruiter

```http
POST /api/auth/register/recruiter/
```

**Purpose**: Create new recruiter account

**Authentication**: None required

**Request Body**:

```json
{
  "email": "recruiter@company.com",
  "password": "securepassword123",
  "company": "company-uuid"
}
```

**Response** (201 Created):

```json
{
  "email": "recruiter@company.com",
  "is_recruiter": true,
  "company": "company-uuid"
}
```

**Requirements**:

- Must specify valid company ID
- Company must exist in database
- Sets `is_recruiter=True` automatically

---

#### Register General User (Admin Only)

```http
POST /api/auth/register/general/
```

**Purpose**: Create admin/staff accounts

**Authentication**: Required (Admin only)

**Request Body**:

```json
{
  "email": "admin@system.com",
  "password": "adminpassword",
  "is_staff": true,
  "is_superuser": false
}
```

**Use Cases**:

- Creating admin accounts
- System maintenance users
- Special permission accounts

---

### User Management

#### List Users (Admin Only)

```http
GET /api/auth/
```

**Purpose**: Get list of all users

**Authentication**: Required (Admin only)

**Response** (200 OK):

```json
[
  {
    "id": "uuid",
    "email": "user@example.com",
    "is_candidate": true,
    "is_recruiter": false,
    "is_active": true
  }
]
```

#### Delete My Account (Candidates Only)

```http
DELETE /api/v1/users/delete/me/
```

**Purpose**: Permanently delete the authenticated candidate's own account

**Authentication**: Required (candidates only — recruiters get 403)

**Request Body**:

```json
{
  "confirm": true,
  "password": "current-password",
  "reason": "Found a job"
}
```

- `confirm` (required) — must be `true`
- `password` — required when the account has a usable password. Accounts created
  through Google or phone OTP have none, so they only send `confirm`
- `reason` (optional) — free-text, logged for product analytics

**Response** (200 OK):

```json
{
  "success": true,
  "message": "Your account has been permanently deleted",
  "timestamp": "2026-07-27T10:00:00+00:00"
}
```

**Behaviour**:

- The user row is deleted; everything owned by the user (profile, resumes,
  applications, saved vacancies, subscriptions, mobile sessions, JWTs) is removed
  by database cascade
- Consent records are immutable legal proof, so they are retained and flagged
  with `consenter_deleted=True` plus a `consenter_email` snapshot
- The current refresh token is blacklisted and all mobile sessions revoked
- `access_token` / `refresh_token` cookies are cleared on the response
- The deletion is immediate and irreversible

## Models

### CustomUser

Base user model extending Django's AbstractBaseUser.

**Key Fields**:

- `id`: UUID primary key
- `email`: Unique email address (used as username)
- `is_candidate`: Boolean flag for candidate users
- `is_recruiter`: Boolean flag for recruiter users
- `is_active`: Account status
- `date_joined`: Registration timestamp

**Authentication**:

- Uses email as USERNAME_FIELD
- Custom user manager for creation logic
- Supports Django admin integration

### Company

Organization model for grouping recruiters.

**Key Fields**:

- `id`: UUID primary key
- `name`: Company name
- `tin`: Tax Identification Number (unique)

**Relationships**:

- One-to-many with Recruiter
- Referenced by Vacancy model

**Validation**:

- TIN must be unique across system
- Name is required

### Candidate

Extends CustomUser for job seekers.

**Inheritance**: One-to-one with CustomUser
**Auto-behavior**: Sets `is_candidate=True` on save
**Related Models**:

- CandidateProfile (from profiles app)
- Resume (from resumes app)
- JobApplication (from applications app)

### Recruiter

Extends CustomUser for hiring managers.

**Key Fields**:

- Inherits from CustomUser
- `company`: ForeignKey to Company

**Auto-behavior**: Sets `is_recruiter=True` on save
**Requirements**: Must be associated with a Company
**Related Models**:

- RecruiterProfile (from profiles app)
- Vacancy (from vacancies app)

## Authentication Flow

### Login Process

1. User submits credentials to `/auth/login/`
2. System validates email/password
3. JWT access and refresh tokens generated
4. Tokens stored in httpOnly cookies
5. User data returned (without tokens)

### Request Authentication

1. Browser automatically sends cookies with requests
2. Custom `CookieJWTAuthentication` class extracts tokens
3. Token validation and user lookup
4. Request proceeds with authenticated user context

### Token Refresh

1. Access token expires (15 minutes)
2. Frontend detects 401 response
3. Automatic call to `/auth/refresh/`
4. New tokens issued and stored in cookies
5. Original request retried

## Frontend Integration

### Initial Authentication Check

```javascript
// Check if user is authenticated on app load
const checkAuth = async () => {
  try {
    await fetch("/auth/verify/", {
      method: "POST",
      credentials: "include", // Important: include cookies
    });
    return true;
  } catch {
    return false;
  }
};
```

### Login Form

```javascript
const login = async (email, password) => {
  const response = await fetch("/auth/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // Include cookies
    body: JSON.stringify({ email, password }),
  });

  if (response.ok) {
    const data = await response.json();
    // Redirect based on user type
    // No need to manually store tokens
  }
};
```

### API Requests

```javascript
// All API requests should include credentials
const apiCall = async (url, options = {}) => {
  return fetch(url, {
    ...options,
    credentials: "include", // Always include cookies
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
};
```

### Automatic Token Refresh

```javascript
// Interceptor for handling token refresh
const apiCallWithRefresh = async (url, options) => {
  let response = await apiCall(url, options);

  if (response.status === 401) {
    // Try to refresh token
    const refreshResponse = await fetch("/auth/refresh/", {
      method: "POST",
      credentials: "include",
    });

    if (refreshResponse.ok) {
      // Retry original request
      response = await apiCall(url, options);
    } else {
      // Redirect to login
      window.location.href = "/login";
    }
  }

  return response;
};
```

## Security Features

### Cookie Security

- **httpOnly**: Prevents XSS access to tokens
- **Secure**: HTTPS-only in production
- **SameSite=Strict**: CSRF protection
- **Automatic expiry**: Tokens have limited lifetime

### Token Management

- **Short-lived access tokens**: 15-minute expiry
- **Refresh token rotation**: Optional security enhancement
- **Token blacklisting**: Logout invalidates tokens
- **Automatic cleanup**: Expired tokens are cleaned up

### Password Security

- **Django's built-in hashing**: PBKDF2 with SHA256
- **Password validation**: Configurable requirements
- **No plaintext storage**: Passwords never stored in readable form

## Error Handling

### Authentication Errors

```json
// Invalid credentials
{
  "detail": "Invalid email or password",
  "code": "invalid_credentials"
}

// Token expired
{
  "detail": "Access token has expired",
  "code": "token_expired"
}

// Token required
{
  "detail": "Access token is required for this endpoint",
  "code": "token_required"
}
```

### Registration Errors

```json
// Email already exists
{
  "email": ["User with this email already exists."]
}

// Invalid company
{
  "company": ["Invalid pk \"invalid-uuid\" - object does not exist."]
}

// Password validation
{
  "password": ["This password is too short. It must contain at least 8 characters."]
}
```

## Backend Architecture

### Custom Authentication Class

```python
class CookieJWTAuthentication(JWTAuthentication):
    """Reads JWT tokens from httpOnly cookies"""

    def authenticate(self, request):
        # Try header authentication first
        header_auth = super().authenticate(request)
        if header_auth:
            return header_auth

        # Fall back to cookie authentication
        access_token = request.COOKIES.get('access_token')
        if access_token:
            return self.get_user_from_token(access_token)
```

### User Type Detection

```python
# In views, detect user type automatically
user = request.user
if user.is_candidate:
    # Handle candidate logic
elif user.is_recruiter:
    # Handle recruiter logic
```

### Permission Classes

```python
# Custom permissions based on user type
class IsCandidateUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_candidate

class IsRecruiterUser(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_recruiter
```

## Configuration

### JWT Settings

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'EXTENDED_REFRESH_TOKEN_LIFETIME': timedelta(days=30),  # web remember_me
    'MOBILE_REFRESH_TOKEN_LIFETIME': timedelta(days=60),  # mobile app, sliding
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}
```

### Mobile App Settings

```bash
# Shared secret the RN app sends on X-Mobile-App-Key. Unset => mobile auth
# endpoints reject every request (fail closed).
MOBILE_APP_API_KEY=

# HMAC key digesting opaque refresh tokens before they're stored. Falls back
# to JWT_SECRET_KEY if unset — set a distinct one in production.
AUTH_REFRESH_PEPPER=

# Idle timeout (days): reset to now + this value on every successful
# /auth/mobile/refresh/ call.
MOBILE_SESSION_IDLE_TTL_DAYS=60
# Absolute timeout (days): fixed from session creation, never extended.
MOBILE_SESSION_ABSOLUTE_TTL_DAYS=180

# Native Google Sign-In — same web OAuth client by default (APP_CLIENT_ID);
# only set this separately if you need a different audience.
GOOGLE_SERVER_CLIENT_ID=

# Lifetime of the one-shot OAuth challenge (nonce/state) returned as
# expires_in by /auth/mobile/oauth/challenge/. It must cover the entire
# native SDK detour (account picker, sign-up, 2FA, consent) — 300s proved
# too short on iOS.
OAUTH_CHALLENGE_TTL_SECONDS=900

# Sign in with Apple (iOS only)
APPLE_TEAM_ID=
APPLE_CLIENT_ID=com.workxplorer.app
APPLE_KEY_ID=
APPLE_PRIVATE_KEY=          # .p8 contents, PEM format
AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY=   # Fernet.generate_key() — encrypts the stored Apple provider refresh token
```

### Phone OTP Settings

```bash
# Eskiz.uz SMS gateway credentials (https://notify.eskiz.uz)
ESKIZ_EMAIL=
ESKIZ_PASSWORD=
ESKIZ_SMS_SENDER=4546  # approved sender nickname; 4546 is Eskiz's shared test sender

OTP_LENGTH=6
OTP_TTL_SECONDS=300               # code validity window
OTP_RESEND_COOLDOWN_SECONDS=60    # minimum gap between sends to the same number
OTP_MAX_SENDS_PER_DAY=5           # per phone number, resets after 24h
OTP_MAX_VERIFY_ATTEMPTS=5         # wrong guesses allowed per code
```

### Cookie Settings

```python
# Development vs Production
COOKIE_SECURE = not DEBUG  # True in production
COOKIE_SAMESITE = 'Strict'
COOKIE_HTTPONLY = True
```

This authentication system provides a secure, scalable foundation for the job board platform with clear separation between user types and robust token management.
