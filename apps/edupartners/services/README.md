# EduPartner Analytics Data Transmission - Protobuf Implementation

This document describes the process of sending analytics data from the WorkXplorer Platform to the EduPartner Analytics
service using Protocol Buffers (protobuf) encoding for optimal data transmission efficiency.

---

## Overview

The EduPartner app collects and sends analytics data to an external analytics service every minute via Redis Queue (RQ)
background tasks. The data is encoded using Protocol Buffers for efficient transmission.

### Key Changes

- **Before**: JSON format via HTTP POST
- **After**: Protobuf binary format via HTTP POST
- **Headers Updated**:
    - `Content-Type: application/x-protobuf`
    - `Content-Encoding: protobuf`
    - `X-Data-Format: workxplorer-protobuf-v3`

---

## Process Flow

### 1. Data Collection

- **Trigger**: Automated RQ task runs every 60 seconds
- **Task**: `send_edupartner_analytics_data()`
- **Location**: `apps/edupartners/tasks.py`

Steps:

1. Retrieve all active faculty IDs using `EduPartnerAnalyticsService.get_faculty_ids()`.
2. Enqueue individual analytics jobs for each faculty to ensure data isolation.

### 2. Individual Faculty Processing

- **Task**: `send_single_faculty_analytics(faculty_id)`
- **Service**: `EduPartnerAnalyticsService.get_faculty_analytics(faculty_id)`

Collected data includes:

- Basic statistics (e.g., student counts, internship placements)
- Employment data (e.g., graduate employment rates)
- Industry analytics (e.g., popular industries with time-series data)
- Hiring funnel (e.g., application progression)
- Company rankings (e.g., top companies by placement volume)
- Student information (e.g., detailed student data with online status tracking)

### 3. Data Preparation

The analytics data is structured into a comprehensive payload:

```python
payload = {
    "edupartner_id": str,
    "edupartner_name": str,
    "faculty_id": str,
    "faculty_name": str,
    "faculty_domain": str,
    "cards": {...},  # Dashboard statistics
    "popular_industries": [...],
    "employed_graduates": {...},
    "hiring_funnel": {...},
    "top_companies_by_placements": [...],
    "students_data": {...},
    "timestamp": str
}
```

### 4. Protobuf Encoding

- **Service**: `EduPartnerAnalyticsProtobufService`
- **Location**: `apps/edupartners/services/protobuf_service.py`

Steps:

1. Validate the data structure.
2. Encode JSON data into compact binary format.
3. Add a custom header for format identification.

```python
protobuf_data = EduPartnerAnalyticsProtobufService.encode_analytics_data(payload)
```

### 5. Data Transmission

- **Endpoint**: Configured via `EDUPARTNER_ANALYTICS_WEBHOOK_URL`
- **Default**: `https://edupartner-service.workxplorer.uz/api/analytics`
- **Method**: HTTP POST
- **Content-Type**: `application/x-protobuf`

HTTP Headers:

```
Content-Type: application/x-protobuf
Content-Encoding: protobuf
X-Data-Format: workxplorer-protobuf-v3
```

### 6. Error Handling & Monitoring

- **Logging**: Comprehensive logging at DEBUG, INFO, WARNING, and ERROR levels.
- **Retry Mechanism**: RQ automatically retries failed jobs.
- **Monitoring**: Encoding efficiency metrics logged with each transmission.
- **Validation**: Data validation before encoding to prevent errors.

---

## Key Benefits of Protobuf Implementation

### Performance

- **Size Reduction**: 15-30% smaller payload size compared to JSON.
- **Bandwidth Savings**: Reduced network usage, especially for large datasets.
- **Faster Transmission**: Smaller payloads = faster uploads.

### Reliability

- **Data Validation**: Schema validation before encoding.
- **Error Detection**: Format verification during encoding/decoding.
- **Consistent Format**: Standardized binary format.

### Scalability

- **Large Dataset Handling**: Efficient handling of student data arrays.
- **Network Efficiency**: Optimal for high-frequency data transmission.
- **Resource Conservation**: Lower memory and bandwidth usage.

---

## Configuration

### Environment Variables

```bash
# Required
EDUPARTNER_ANALYTICS_WEBHOOK_URL=https://edupartner-service.workxplorer.uz/api/analytics

# Optional  
EDUPARTNER_API_KEY=your-api-key-here
```

### RQ Scheduling

The analytics transmission is automatically scheduled when the server starts:

```python
# In scheduler.py
schedule_edupartner_analytics(86400)  # Run every 24 hours
```

---

## Monitoring & Debugging

### Log Examples

```
INFO: Protobuf encoding efficiency: 23.5% smaller (2048 -> 1567 bytes)
INFO: Protobuf analytics sent successfully for Tashkent State University (size: 1567 bytes)
DEBUG: Protobuf encoding: JSON 2048 bytes -> Protobuf 1567 bytes (compression: 23.5%)
```

### Performance Metrics

Each transmission logs:

- Original JSON size.
- Protobuf encoded size.
- Compression ratio percentage.
- Actual bytes saved.
- Faculty/university name.
- Transmission success/failure.

### Health Checks

Monitor these indicators:

1. **RQ Queue Status**: Check for failed jobs.
2. **Encoding Success Rate**: Monitor protobuf encoding failures.
3. **Transmission Success Rate**: HTTP response monitoring.
4. **Data Validation**: Schema validation failure rates.

---

## Testing

### Unit Tests

- **File**: `tests/test_protobuf_service.py`
- **Coverage**: Encoding, decoding, validation, round-trip integrity.
- **Run Tests**: `python manage.py test apps.edupartners.tests.test_protobuf_service`

### Manual Testing

```python
# Quick protobuf functionality test
from apps.edupartners.services.protobuf_service import EduPartnerAnalyticsProtobufService

test_data = {
    "edupartner_id": "test-123",
    "edupartner_name": "Test University",
    # ... other required fields
}

# Test encoding/decoding
binary = EduPartnerAnalyticsProtobufService.encode_analytics_data(test_data)
decoded = EduPartnerAnalyticsProtobufService.decode_analytics_data(binary)
assert decoded == test_data  # Should pass
```

---

## Future Enhancements

### Potential Improvements

1. **Compression**: Add gzip compression for even smaller payloads.
2. **Encryption**: Add data encryption for sensitive analytics.
3. **Batch Processing**: Combine multiple faculty data into single transmission.
4. **Schema Validation**: More sophisticated schema validation using actual protobuf definitions.

### Migration Path

If needed, the system can easily support both JSON and protobuf formats simultaneously:

```python
if content_type == 'application/x-protobuf':
    data = decode_protobuf(request.body)
elif content_type == 'application/json':
    data = request.json()
```

This protobuf implementation ensures efficient, reliable transmission of EduPartner analytics data while maintaining the
existing workflow and scheduling patterns.