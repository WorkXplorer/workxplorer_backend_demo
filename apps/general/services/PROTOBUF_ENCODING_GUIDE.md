# Protocol Buffers (Protobuf) Encoding Guide for HR Analytics

## Overview

The WorkXplorer platform uses **Protocol Buffers (Protobuf)** for efficient binary encoding of HR analytics data sent to
external services. This approach provides significant bandwidth savings (typically 40-60% smaller than JSON) and ensures
type safety.

## Table of Contents

1. [What is Protocol Buffers?](#what-is-protocol-buffers)
2. [Architecture Overview](#architecture-overview)
3. [Data Flow](#data-flow)
4. [Schema Definition](#schema-definition)
5. [Encoding Process](#encoding-process)
6. [Decoding Process](#decoding-process)
7. [Implementation Details](#implementation-details)
8. [Usage Examples](#usage-examples)
9. [Troubleshooting](#troubleshooting)

---

## What is Protocol Buffers?

**Protocol Buffers (Protobuf)** is a language-neutral, platform-neutral, extensible mechanism developed by Google for
serializing structured data. It's like JSON or XML, but:

- **Smaller**: 3-10x smaller than XML, 20-100x faster
- **Type-safe**: Strongly typed with schema validation
- **Backward/Forward compatible**: Easy to evolve schemas over time
- **Binary format**: More efficient for network transmission

---

## Architecture Overview

```
┌─────────────────────┐
│  WorkXplorer API    │
│  (Django/Python)    │
└──────────┬──────────┘
           │
           │ 1. Collect Analytics Data (Dict)
           ↓
┌─────────────────────┐
│  Analytics Service  │
│  (analytics.py)     │
└──────────┬──────────┘
           │
           │ 2. Build Payload (Dict)
           ↓
┌─────────────────────┐
│ Protobuf Service    │
│(protobuf_service.py)│
└──────────┬──────────┘
           │
           │ 3. Encode to Binary
           ↓
┌─────────────────────┐
│  Binary Data        │
│  (bytes)            │
└──────────┬──────────┘
           │
           │ 4. HTTP POST
           ↓
┌─────────────────────┐
│  HR Analytics       │
│  External Service   │
└──────────┬──────────┘
           │
           │ 5. Decode Binary
           ↓
┌─────────────────────┐
│  Analytics Data     │
│  (Dict/Object)      │
└─────────────────────┘
```

---

## Data Flow

### Step 1: Data Collection

The `analytics.py` module collects HR metrics:

- Average vacancy view time
- Open vacancies count
- Applications count
- Vacancy views
- Average candidate age
- Top industries
- Hiring dynamics
- Application response dynamics

### Step 2: Payload Construction

The `webhook_sender.py` builds a structured payload:

```python
payload = {
    "source": "workxplorer",
    "timestamp": "2025-12-19T12:00:00Z",
    "meta": {
        "env": "production",
        "company_id": "uuid-here"
    },
    "company": { ... },
    "cards": { ... },
    "analytics": { ... },
    "analytics_timestamp": "2025-12-19T12:00:00Z"
}
```

### Step 3: Protobuf Encoding

The `HRAnalyticsProtobufService.encode_analytics_data()` method:

1. **Validates** the payload structure
2. **Converts** Python dict to Protobuf message objects
3. **Serializes** to binary format
4. **Adds** WorkXplorer header (WKXP + version + length)
5. **Returns** final binary data

### Step 4: Binary Transmission

The encoded binary data is sent via HTTP POST:

```python
requests.post(
    url,
    data=protobuf_data,
    headers={
        "Content-Type": "application/x-protobuf",
        "Content-Encoding": "protobuf",
        "X-Data-Format": "workxplorer-protobuf-v3"
    }
)
```

### Step 5: Decoding (Receiver Side)

The receiving service uses `HRAnalyticsProtobufService.decode_analytics_data()`:

1. **Verifies** WorkXplorer header
2. **Checks** protocol version
3. **Extracts** binary payload
4. **Parses** Protobuf message
5. **Converts** back to Python dict/object

---

## Schema Definition

The schema is defined in `hr_analytics.proto`:

```protobuf
syntax = "proto3";

package hr.analytics;

message HRAnalyticsData {
    string source = 1;
    string timestamp = 2;
    Meta meta = 3;
    Company company = 4;
    Cards cards = 5;
    Analytics analytics = 6;
    string analytics_timestamp = 7;
}

message Cards {
    AverageViewTime average_view_time = 1;
    OpenVacancies open_vacancies = 2;
    ApplicationsCount applications_count = 3;
    VacancyViews vacancy_views = 4;
    AverageCandidateAge average_candidate_age = 5;
}

// ... more message definitions
```

### Compiling the Schema

To generate Python code from `.proto` file:

```bash
cd apps/general/services/analytics
python -m grpc_tools.protoc -I. --python_out=. hr_analytics.proto
```

This generates `hr_analytics_pb2.py` containing message classes.

---

## Encoding Process

### High-Level Flow

```python
from apps.general.services.analytics import HRAnalyticsProtobufService

# 1. Prepare analytics data
analytics_data = {
    "source": "workxplorer",
    "timestamp": timezone.now().isoformat(),
    "meta": {"env": "production", "company_id": "123"},
    "company": {...},
    "cards": {...},
    "analytics": {...}
}

# 2. Validate data
is_valid = HRAnalyticsProtobufService.validate_analytics_data(analytics_data)

# 3. Encode to binary
binary_data = HRAnalyticsProtobufService.encode_analytics_data(analytics_data)

# 4. Get encoding stats
info = HRAnalyticsProtobufService.get_encoding_info(analytics_data)
print(f"Compression: {info['efficiency_gain']}")
```

### Binary Format Structure

```
┌──────────────────────────────────────────────────────┐
│  WKXP  │  Ver  │  Length  │  Protobuf Binary Data   │
│ (4 B)  │ (1 B) │  (4 B)   │  (variable length)      │
└──────────────────────────────────────────────────────┘
```

- **WKXP**: WorkXplorer header identifier (4 bytes)
- **Ver**: Protocol version = 3 (1 byte)
- **Length**: Payload length in little-endian (4 bytes)
- **Data**: Serialized protobuf message (variable)

### Type Conversion Helpers

The service provides safe type conversion:

```python
# String conversion
HRAnalyticsProtobufService._ensure_string(value)  # Returns "" if None

# Integer conversion
HRAnalyticsProtobufService._ensure_int(value)     # Returns 0 if None/invalid

# Float conversion
HRAnalyticsProtobufService._ensure_float(value)   # Returns 0.0 if None/invalid

# Boolean conversion
HRAnalyticsProtobufService._ensure_bool(value)    # Returns False if None
```

---

## Decoding Process

### Receiver-Side Implementation

```python
from apps.general.services.analytics import HRAnalyticsProtobufService

# 1. Receive binary data from HTTP request
binary_data = request.body

# 2. Decode to Python dict
analytics_data = HRAnalyticsProtobufService.decode_analytics_data(binary_data)

# 3. Access the data
print(analytics_data['company']['name'])
print(analytics_data['cards']['average_view_time']['value'])
```

### Validation Steps

The decoder performs:

1. **Header validation**: Checks for "WKXP" magic bytes
2. **Version check**: Ensures protocol version = 3
3. **Length verification**: Validates payload size
4. **Protobuf parsing**: Deserializes binary to message
5. **Dict conversion**: Converts message to Python dict

---

## Implementation Details

### Key Files

| File                  | Purpose                                  |
|-----------------------|------------------------------------------|
| `hr_analytics.proto`  | Schema definition (IDL)                  |
| `hr_analytics_pb2.py` | Compiled Python classes (auto-generated) |
| `protobuf_service.py` | Encoding/decoding service                |
| `webhook_sender.py`   | Sends protobuf data via HTTP             |
| `analytics.py`        | Collects HR metrics                      |

### Message Building

Each complex type has a builder method:

```python
# Build Meta message
meta = hr_analytics_pb2.Meta()
meta.env = "production"
meta.company_id = "uuid"

# Build Company message
company = hr_analytics_pb2.Company()
company.id = "uuid"
company.name = "Company Name"

# Build nested Cards
cards = hr_analytics_pb2.Cards()
cards.average_view_time.value = 45.5
cards.average_view_time.unit = "seconds"
```

### Repeated Fields

For lists, use `.append()`:

```python
# Industries list
for industry in top_industries:
    ind_msg = analytics.top_industries.industries.add()
    ind_msg.industry_id = industry['id']
    ind_msg.industry_name = industry['name']
```

### Optional Fields

Proto3 uses default values for missing fields:

- Strings: `""`
- Numbers: `0`
- Bools: `false`

To check if optional field is set:

```python
if message.HasField('optional_field'):
    value = message.optional_field
```

---

## Usage Examples

### Example 1: Sending HR Analytics for a Company

```python
from apps.general.tasks import send_single_company_analytics
import django_rq

# Enqueue background job
queue = django_rq.get_queue("default")
job = queue.enqueue(
    send_single_company_analytics,
    "uuid-here",
    analytics_period_days=30
)

print(f"Job enqueued: {job.id}")
```

### Example 2: Manual Encoding/Decoding

```python
from apps.general.services.analytics import HRAnalyticsProtobufService

# Encode
data = {
    "source": "workxplorer",
    "timestamp": "2025-12-19T12:00:00Z",
    "meta": {"env": "test", "company_id": "123"},
    "company": {"id": "123", "name": "Test Co", ...},
    "cards": {...},
    "analytics": {...}
}

binary = HRAnalyticsProtobufService.encode_analytics_data(data)

# Decode
decoded = HRAnalyticsProtobufService.decode_analytics_data(binary)

assert decoded == data  # Roundtrip successful
```

### Example 3: Checking Compression

```python
info = HRAnalyticsProtobufService.get_encoding_info(analytics_data)

print(f"JSON size: {info['json_size_bytes']} bytes")
print(f"Protobuf size: {info['protobuf_size_bytes']} bytes")
print(f"Compression: {info['compression_ratio_percent']}%")
print(f"Saved: {info['size_reduction_bytes']} bytes")
print(f"Format: {info['format']}")
```

---

## Troubleshooting

### Common Issues

#### 1. Module Import Error

```
ModuleNotFoundError: No module named 'hr_analytics_pb2'
```

**Solution**: Compile the proto file:

```bash
cd apps/general/services/analytics
python -m grpc_tools.protoc -I. --python_out=. hr_analytics.proto
```

#### 2. Validation Failure

```
ERROR: Missing required field: company.id
```

**Solution**: Ensure all required fields are present in payload.

#### 3. Decoding Error

```
ValueError: Invalid protobuf data: bad header
```

**Solution**: Verify the binary data starts with "WKXP" header.

#### 4. Type Conversion Warning

```
WARNING: _ensure_string received a dict where a string was expected
```

**Solution**: Fix upstream data to pass proper types. The service handles it but logs a warning.

### Debugging Tips

1. **Enable debug logging**:
   ```python
   import logging
   logging.getLogger('apps.general.services.analytics').setLevel(logging.DEBUG)
   ```

2. **Inspect binary data**:
   ```python
   print(binary_data[:9].hex())  # Should start with "574b5850" (WKXP)
   ```

3. **Validate before encoding**:
   ```python
   if HRAnalyticsProtobufService.validate_analytics_data(data):
       binary = HRAnalyticsProtobufService.encode_analytics_data(data)
   ```

4. **Check encoding stats**:
   ```python
   info = HRAnalyticsProtobufService.get_encoding_info(data)
   if 'error' in info:
       print(f"Encoding failed: {info['error']}")
   ```

---

## Comparison: HR Analytics vs EduPartner Analytics

Both services use the same protobuf approach:

| Aspect           | HR Analytics                       | EduPartner Analytics                 |
|------------------|------------------------------------|--------------------------------------|
| **Proto File**   | `hr_analytics.proto`               | `analytics.proto`                    |
| **Service**      | `HRAnalyticsProtobufService`       | `EduPartnerAnalyticsProtobufService` |
| **Location**     | `apps/general/services/analytics/` | `apps/edupartners/services/`         |
| **Header**       | `WKXP` + Version 3                 | `WKXP` + Version 3                   |
| **Content-Type** | `application/x-protobuf`           | `application/x-protobuf`             |
| **Use Case**     | Company HR metrics                 | Faculty/Student metrics              |

Both follow identical patterns for consistency across the platform.

---

## Best Practices

1. **Always validate** data before encoding
2. **Use type helpers** (`_ensure_string`, `_ensure_int`, etc.)
3. **Log compression stats** for monitoring
4. **Handle errors gracefully** with try/except
5. **Keep proto schema backward-compatible** when evolving
6. **Document schema changes** in version control
7. **Test roundtrip encoding/decoding** in unit tests

---

## Performance Metrics

Typical compression ratios for HR analytics data:

| Data Size (JSON) | Protobuf Size | Compression Ratio | Savings    |
|------------------|---------------|-------------------|------------|
| 100 KB           | 40-50 KB      | 50-60%            | 50-60 KB   |
| 500 KB           | 200-250 KB    | 50-60%            | 250-300 KB |
| 1 MB             | 400-500 KB    | 50-60%            | 500-600 KB |

**Benefits**:

- Reduced bandwidth usage
- Faster transmission over network
- Lower cloud egress costs
- Better mobile performance

---

## References

- [Protocol Buffers Documentation](https://developers.google.com/protocol-buffers)
- [Proto3 Language Guide](https://developers.google.com/protocol-buffers/docs/proto3)
- [Python Protobuf Tutorial](https://developers.google.com/protocol-buffers/docs/pythontutorial)
- [gRPC Python Tools](https://grpc.io/docs/languages/python/quickstart/)

---

## Changelog

### v3 (Current)

- Pure protobuf binary encoding (no JSON inside)
- Type-safe message construction
- Backward compatible with schema evolution

### v2 (Deprecated)

- JSON inside protobuf wrapper
- Less efficient compression

### v1 (Deprecated)

- Plain JSON transmission
- No compression

---

## Contact

For questions or issues with protobuf implementation:

- Check logs: `/var/log/workxplorer/`
- File bug: Internal issue tracker
- Documentation: This file

---

**Last Updated**: 2025-12-19  
**Version**: 3.0  
**Maintained by**: WorkXplorer Backend Team
