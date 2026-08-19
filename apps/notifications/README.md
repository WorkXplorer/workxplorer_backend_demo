# Notifications App Documentation

## 1. Header & Overview

**Notifications App** - Push notification and in-app notification system for WorkXplorer

This app provides a comprehensive notification infrastructure with Firebase Cloud Messaging (FCM) integration,
database-stored notifications, device management, and real-time push notifications. It supports both broadcast
notifications and targeted user/group notifications with delivery tracking.

## 2. Features

- Firebase Cloud Messaging (FCM) integration for push notifications
- Database-stored notifications with read/unread tracking
- Device registration and management for multiple devices per user
- Bulk notification sending with batch processing
- Notification delivery logging and statistics
- Caching layer for optimized performance (5-minute cache)
- Admin-only broadcast notifications to all users
- Targeted notifications to specific users or groups
- Multicast messaging for efficient batch delivery
- Automatic cache invalidation on updates
- Notification filtering by type and read status
- Pagination support with customizable page sizes

## 3. API Endpoints

### User Endpoints

#### Get User Notifications

```
GET /api/notifications/
```

**Authentication**: Required

**Query Parameters**:

- `page` (int, optional): Page number (default: 1)
- `page_size` (int, optional): Items per page (default: 20)
- `only_unread` (bool, optional): Filter unread only
- `type` (string, optional): Filter by notification type

**Response**:

```json
{
  "notifications": [
    {
      "id": 12,
      "title": "Application Update",
      "message": "Your job application has been viewed",
      "created_at": "2025-09-20T12:45:00Z",
      "notification_type": "application_offered",
      "is_read": false,
      "read_at": null,
      "sent_count": 100,
      "success_count": 98,
      "failure_count": 2
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 5,
    "total_count": 100,
    "has_next": true,
    "has_previous": false,
    "page_size": 20
  },
  "unread_count": 34
}
```

**Features**:

- Cached for 5 minutes per query combination
- Optimized with select_related and prefetch_related
- Only returns user's own notifications

---

#### Register Device

```
POST /api/notifications/register-device/
```

**Authentication**: Required

**Request**:

```json
{
  "registration_id": "fcm_device_token_123456",
  "type": "android"
}
```

**Response**:

```json
{
  "message": "Device registered successfully.",
  "device_id": 101
}
```

**Features**:

- Creates or updates existing device
- Reactivates inactive devices
- Supports android, ios, web types

---

#### Mark Notification as Read

```
PATCH /api/notifications/mark-as-read/<int:notification_id>/
```

**Authentication**: Required

**Response**:

```json
{
  "message": "Notification marked as read"
}
```

**Features**:

- Updates is_read flag and read_at timestamp
- Invalidates user notification cache
- User can only mark their own notifications

---

#### Bulk Mark as Read

```
PATCH /api/notifications/bulk-mark-as-read/
```

**Authentication**: Required

**Response**:

```json
{
  "message": "5 notifications marked as read",
  "updated_count": 5
}
```

**Features**:

- Marks all unread notifications as read
- Bulk update for efficiency
- Clears all notification caches

---

### Admin Endpoints

#### Send to All Devices

```
POST /api/notifications/send/
```

**Authentication**: Admin only

**Request**:

```json
{
  "title": "Important Update",
  "message": "Please check the latest updates in your app",
  "data": {
    "key1": "value1",
    "key2": "value2"
  },
  "sent_to_all": true
}
```

**Response**:

```json
{
  "message": "Notification sent.",
  "sent_count": 120,
  "success_count": 118,
  "failure_count": 2,
  "notification_id": 45,
  "detail": "Notification dispatched to devices."
}
```

**Features**:

- Broadcasts to all registered devices
- Batch FCM multicast messaging
- Tracks delivery statistics

---

#### Send to Specific User

```
POST /api/notifications/send-to-user/
```

**Authentication**: Admin only

**Request**:

```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "title": "Personal Message",
  "message": "You have a new job match!",
  "notification_type": "new_job_match",
  "data": {
    "job_id": "456",
    "redirect_url": "/jobs/456"
  }
}
```

**Response**:

```json
{
  "message": "Notification sent successfully.",
  "notification_id": 123,
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_email": "user@example.com",
  "push_notification_sent": true,
  "push_notification_message": "Sent to 2 out of 2 devices",
  "devices_count": 2,
  "success_count": 2,
  "failure_count": 0
}
```

**Features**:

- Validates UUID format
- Validates notification type
- Creates database notification
- Sends push to all user devices
- Multicast batch sending

---

#### Send to Multiple Users

```
POST /api/notifications/send-to-multiple-users/
```

**Authentication**: Admin only

**Request**:

```json
{
  "user_ids": [
    "123e4567-e89b-12d3-a456-426614174000",
    "987fcdeb-51d2-43a8-b123-123456789abc"
  ],
  "title": "Group Message",
  "message": "Important announcement for selected users",
  "notification_type": "platform_announcement",
  "data": {
    "announcement_id": "789"
  }
}
```

**Response**:

```json
{
  "message": "Notifications sent successfully.",
  "notification_id": 456,
  "total_users": 2,
  "total_devices": 5,
  "push_notifications_sent": 5,
  "not_found_user_ids": [],
  "user_results": [
    {
      "user_id": "123e4567-e89b-12d3-a456-426614174000",
      "email": "user1@example.com",
      "devices_count": 3,
      "success_count": 3,
      "success": true
    }
  ]
}
```

**Features**:

- Bulk creates notification recipients
- Sends to all devices of all users
- Returns detailed per-user results
- Reports not found user IDs

---

#### Notify Recruiters (Job Application)

```
POST /api/notifications/send-to-recruiters/
```

**Authentication**: Required (Candidate)

**Request**:

```json
{
  "job_application_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response**:

```json
{
  "message": "Notification sent successfully to recruiters",
  "job_application_id": "550e8400-e29b-41d4-a716-446655440000",
  "recruiters_notified": 5,
  "push_notifications_sent": 5,
  "notification_id": "123"
}
```

**Features**:

- Triggered by candidate job application
- Notifies all company recruiters
- Optimized with prefetch_related
- Batch FCM multicast sending
- Only sends if vacancy is active

## 4. Models

### Notification

Core notification record with statistics tracking.

**Fields**:

- `title`: CharField(max_length=255, indexed) - Notification title
- `message`: TextField - Notification body content
- `notification_type`: CharField - Type from NotificationType choices
- `data`: JSONField - Additional custom data
- `sent_to_all`: BooleanField(indexed) - Broadcast flag
- `sent_count`: PositiveIntegerField - Total sent
- `success_count`: PositiveIntegerField - Successful deliveries
- `failure_count`: PositiveIntegerField - Failed deliveries
- `created_by`: ForeignKey to CustomUser - Creator (nullable)
- `created_at`, `updated_at`: Timestamps

**NotificationType Choices**:

- application_accepted
- application_rejected
- application_offered
- new_job_match
- platform_announcement
- profile_update_reminder
- interview_scheduled
- interview_reminder

**Properties**:

- `success_rate`: Calculates percentage of successful deliveries

**Features**:

- Composite indexes for performance
- Tracks delivery statistics
- Supports custom data payloads

**Use Cases**:

- Job application status updates
- Interview scheduling
- Platform announcements
- Profile reminders

---

### NotificationRecipient

Links notifications to specific users with read tracking.

**Fields**:

- `notification`: ForeignKey to Notification - Parent notification
- `user`: ForeignKey to CustomUser - Recipient
- `is_read`: BooleanField(indexed, default=False) - Read status
- `read_at`: DateTimeField(nullable) - Read timestamp
- `created_at`, `updated_at`: Timestamps

**Unique Constraint**: (notification, user) - Prevents duplicates

**Methods**:

- `mark_as_read()`: Updates status and timestamp (idempotent)

**Features**:

- Composite indexes for user+read queries
- Unique constraint prevents duplicate recipients
- Cascade deletion with notification

**Use Cases**:

- User inbox management
- Unread count calculation
- Read tracking analytics

---

### NotificationLog

Tracks individual device delivery attempts.

**Fields**:

- `notification`: ForeignKey to Notification - Parent notification
- `user`: ForeignKey to CustomUser - Recipient user
- `device`: ForeignKey to FCMDevice - Target device
- `status`: CharField - Status from Status choices (sent/failed/delivered)
- `error_message`: TextField(nullable) - Failure details
- `created_at`, `updated_at`: Timestamps

**Status Choices**:

- sent: Successfully sent to FCM
- failed: FCM send failed
- delivered: Confirmed delivery

**Features**:

- Tracks per-device delivery
- Stores error messages for debugging
- Orders by newest first

**Use Cases**:

- Debugging failed deliveries
- Device-level analytics
- Audit trail

## 5. Business Logic

### FCM Push Notification Flow

**Single Device Send**:

```python
fcm_message = messaging.Message(
    notification=messaging.Notification(
        title=title,
        body=message,
    ),
    data=data_dict,  # All values must be strings
    token=device.registration_id,
)
response = messaging.send(fcm_message)
```

**Multicast Batch Send** (optimized):

```python
# Send to up to 500 devices at once
multicast_message = messaging.MulticastMessage(
    notification=messaging.Notification(
        title=title,
        body=message,
    ),
    data=string_data,
    tokens=device_tokens[:500]  # FCM limit
)
batch_response = messaging.send_multicast(multicast_message)
success_count = batch_response.success_count
```

### Notification Creation Workflow

**Step 1: Create Database Record**

```python
notification = Notification.objects.create(
    title=title,
    message=message,
    notification_type=notification_type,
    data=custom_data,
    sent_to_all=False,
    created_by=admin_user
)
```

**Step 2: Create Recipients**

```python
# Bulk create for efficiency
recipients = [
    NotificationRecipient(notification=notification, user=user)
    for user in target_users
]
NotificationRecipient.objects.bulk_create(recipients)
```

**Step 3: Send Push Notifications**

```python
# Get all active devices
devices = FCMDevice.objects.filter(user__in=users, active=True)

# Batch send with multicast
tokens = [d.registration_id for d in devices]
response = messaging.send_multicast(multicast_message)

# Update statistics
notification.sent_count = len(users)
notification.success_count = response.success_count
notification.failure_count = response.failure_count
notification.save()
```

**Step 4: Clear Caches**

```python
# Invalidate user caches
for user_id in user_ids:
    cache.delete(f"unread_count_user_{user_id}")
    cache.delete_pattern(f"notifications_user_{user_id}_*")
```

### Cache Strategy

**Cache Keys**:

```python
CACHE_KEY_UNREAD_COUNT = "unread_count_user_{user_id}"
CACHE_KEY_NOTIFICATIONS_PATTERN = "notifications_user_{user_id}_*"
```

**Query Caching**:

```python
# Cache key includes all query parameters
cache_key = f"notifications_user_{user_id}_page_{page}_size_{page_size}_unread_{only_unread}_type_{type}"
cached_data = cache.get(cache_key)
if cached_data:
    return cached_data

# Query database and cache for 5 minutes
data = fetch_from_database()
cache.set(cache_key, data, 300)
```

**Cache Invalidation**:

- On mark as read: Clear user's unread count and notification pages
- On bulk mark as read: Clear all user notification caches
- On new notification: Clear recipient notification caches

### Recruiter Notification Optimization

**N+1 Query Prevention**:

```python
# Single query with prefetch_related
recruiters = Recruiter.objects.filter(
    company=company,
    is_active=True
).select_related(
    'customuser_ptr'
).prefetch_related(
    'fcmdevice_set'
).only(
    'customuser_ptr__id',
    'customuser_ptr__email',
    'customuser_ptr__is_active'
)

# All data loaded, no additional queries in loop
for recruiter in recruiters:
    devices = recruiter.fcmdevice_set.all()  # No query, uses prefetched data
```

**Batch Push Sending**:

```python
# Collect all tokens first
all_tokens = []
for recruiter in recruiters:
    for device in recruiter.fcmdevice_set.all():
        if device.active:
            all_tokens.append(device.registration_id)

# Send to all at once (multicast)
response = messaging.send_multicast(multicast_message)
```

## 6. Multi-Language Support

Not implemented. Notification content is stored in the language it was created.

**Potential Enhancement**:

- Store notification templates with translation keys
- Use django-modeltranslation for title/message fields
- Send localized content based on user language preference

## 7. Error Responses

### 400 Bad Request

**Missing fields**:

```json
{ "error": "Title, message, and sent_to_all are required." }
```

**Invalid UUID**:

```json
{ "error": "Invalid user_id format. Must be a valid UUID." }
```

**Invalid notification type**:

```json
{ "error": "Invalid notification_type. Must be one of: [...]" }
```

**No active devices**:

```json
{ "error": "No active devices found for user." }
```

### 401 Unauthorized

```json
{ "detail": "Authentication credentials were not provided." }
```

### 403 Forbidden

```json
{ "detail": "You do not have permission to perform this action." }
```

### 404 Not Found

**Notification not found**:

```json
{ "error": "Notification not found" }
```

**User not found**:

```json
{ "error": "User not found or inactive." }
```

**No devices**:

```json
{ "error": "No active devices found." }
```

### 500 Internal Server Error

```json
{ "error": "Failed to send notifications. Please try again." }
```

## 8. Security

**Permission Classes**:

- User endpoints: IsAuthenticated
- Admin endpoints: IsAuthenticated + IsAdminUser
- Recruiter notification: IsAuthenticated (candidates only)

**Data Access Control**:

- Users see only their own notifications
- Users can only mark their own notifications as read
- Admin required for broadcast and targeted notifications

**Input Validation**:

- UUID format validation for user_ids
- Notification type enum validation
- Required field validation
- Data type validation (arrays, objects)

**FCM Security**:

- Device tokens validated by Firebase
- All FCM data values converted to strings
- Error handling prevents token exposure in logs

## 9. Testing

### Run Tests

```bash
python manage.py test apps.notifications
python manage.py test apps.notifications.tests.test_models
python manage.py test apps.notifications.tests.test_views
```

### Model Test Coverage

- Notification creation and statistics
- Success rate calculation
- NotificationRecipient unique constraint
- mark_as_read method idempotency
- NotificationLog status tracking
- Model ordering and string representations

### View Test Coverage

- Authentication requirements
- Permission enforcement (admin only)
- Notification filtering (unread, type)
- Pagination functionality
- Device registration and updates
- Mark as read (single and bulk)
- Send to all devices (mocked FCM)
- Send to specific user
- Send to multiple users
- Recruiter notifications
- Cache invalidation
- Invalid input handling

## 10. Admin Interface

### NotificationAdmin

- **List display**: Title, type, sent/success/failure counts, timestamps, creator
- **Search**: Title, message, notification_type
- **Filters**: Notification type, created_at
- **Read-only**: Statistics fields, timestamps
- **Ordering**: Newest first

### NotificationRecipientAdmin

- **List display**: Notification, user, is_read, read_at, created_at
- **Search**: Notification title, username, email
- **Filters**: is_read, created_at
- **Read-only**: Timestamps
- **Ordering**: Newest first

### NotificationLogAdmin

- **List display**: Notification, user, status, created_at
- **Search**: Notification title, username, email, status
- **Filters**: Status, created_at
- **Read-only**: Timestamps
- **Ordering**: Newest first

## 11. Performance

### Current Optimizations

- 5-minute query result caching
- select_related for notification joins
- prefetch_related for related objects
- Bulk create for notification recipients
- FCM multicast batch sending (up to 500 devices)
- Composite database indexes
- Bulk cache deletion
- Optimized query with .only() for minimal fields

### Query Patterns

```python
# Get notifications: 2 queries (recipients + notifications)
NotificationRecipient.objects.filter(user=user).select_related('notification')

# Send to recruiters: 1 query with prefetch
Recruiter.objects.filter(company=company).prefetch_related('fcmdevice_set')

# Multicast send: 1 FCM API call for 500 devices
messaging.send_multicast(multicast_message)
```

### Recommendations

**Redis Cache Backend**:

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

**Celery for Async Sending**:

```python
@shared_task
def send_notification_async(notification_id, user_ids):
    # Send notifications in background
    # Prevents API timeout for large batches
    pass
```

**Database Indexes**:

```python
# Already implemented
class Meta:
    indexes = [
        models.Index(fields=['-created_at', 'notification_type']),
        models.Index(fields=['user', 'is_read']),
    ]
```

## 12. Integration Points

### Used By Other Apps

- Applications app: Sends notifications when job applications status changes
- Vacancies app: Could notify about new job matches
- Authentication app: Could send welcome/verification notifications

### Provides Services

- NotificationService: Reusable service layer for FCM operations
- Device management API
- Notification delivery tracking

### Dependencies

- **firebase-admin**: FCM push notifications
- **fcm-django**: Django integration for FCM devices
- **Django cache framework**: Result caching
- **Redis**: Cache backend (recommended)

### External APIs

- Firebase Cloud Messaging (FCM) for push delivery
- Device token validation via FCM

---

## Tutorial: Understanding the Notification System

### How Push Notifications Work

**Registration Flow**:

```
1. User installs app → Gets FCM token from Firebase
2. App sends token to /register-device/ endpoint
3. Server stores token in FCMDevice model
4. User now registered to receive notifications
```

**Sending Flow**:

```
1. Admin/System creates Notification record
2. Creates NotificationRecipient for each user
3. Collects all FCM tokens for recipients
4. Sends batch multicast to Firebase
5. Firebase delivers to user devices
6. Server updates success/failure statistics
```

### Multicast vs Individual Sending

**Individual** (slow):

```python
# 100 devices = 100 API calls
for device in devices:
    messaging.send(message, device.token)
```

**Multicast** (fast):

```python
# 100 devices = 1 API call (up to 500 limit)
messaging.send_multicast(message, [all_tokens])
```

### Cache Strategy Example

**Without Cache** (slow):

```python
# Every request hits database
notifications = NotificationRecipient.objects.filter(user=user).select_related(...)
# Query time: ~50ms per request
```

**With Cache** (fast):

```python
# First request hits database, subsequent requests use cache
cached = cache.get(cache_key)
if cached:
    return cached  # ~1ms
# Only query database if cache miss
```

### When to Use Each Endpoint

- **send/**: Admin broadcasts to everyone (platform announcements)
- **send-to-user/**: Admin sends to one user (personalized messages)
- **send-to-multiple-users/**: Admin sends to specific group
- **send-to-recruiters/**: Automatic on job application (system-triggered)

This architecture ensures reliable, scalable notification delivery with comprehensive tracking and optimized
performance.
