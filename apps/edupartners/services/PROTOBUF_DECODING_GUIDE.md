# Protobuf Data Decoding Instructions

This document provides detailed instructions for decoding the protobuf-encoded analytics data sent from WorkXplorer Platform to external services.

## Overview

WorkXplorer Platform sends analytics data in a custom protobuf binary format that provides significant size reduction while maintaining data integrity. This guide explains how to decode and process this data.

## Data Format Specification

### Binary Format Structure
```
[Header: 4 bytes] + [Version: 1 byte] + [Length: 4 bytes] + [PROTOBUF_BINARY: N bytes]
```

- **Header**: `WKXP` (WorkXplorer Protobuf identifier)
- **Version**: `0x03` (Format version 3 - Pure protobuf binary)
- **Length**: Protobuf data length in little-endian format
- **Protobuf Data**: Actual binary protobuf using Google's wire format

### Content-Type Headers
```
Content-Type: application/x-protobuf
Content-Encoding: protobuf
X-Data-Format: workxplorer-protobuf-v3
```

## Decoding Implementation

### Python Implementation

#### Method 1: Using WorkXplorer Protobuf Service
```python
import requests
from apps.edupartners.services.protobuf_service import EduPartnerAnalyticsProtobufService

def handle_protobuf_webhook(request):
    """Handle incoming protobuf analytics data."""
    try:
        # Get binary data from request
        binary_data = request.body
        
        # Decode protobuf data
        analytics_data = EduPartnerAnalyticsProtobufService.decode_analytics_data(binary_data)
        
        # Process the decoded data
        process_analytics(analytics_data)
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Failed to decode protobuf data: {e}")
        return {"status": "error", "message": str(e)}

def process_analytics(data):
    """Process decoded analytics data."""
    print(f"Received data for: {data['edupartner_name']}")
    print(f"Faculty: {data.get('faculty_name', 'N/A')}")
    print(f"Students on internships: {data['cards']['students_on_internships']['value']}")
    # ... process other fields
```

#### Method 2: Manual Decoding (Standalone)
```python
import json

# Current WorkXplorer protobuf version
WORKXPLORER_PROTOBUF_VERSION = 3

def decode_workxplorer_protobuf(binary_data: bytes) -> dict:
    """
    Decode WorkXplorer protobuf binary data to dictionary.
    
    Args:
        binary_data: Binary protobuf data from HTTP request
        
    Returns:
        dict: Decoded analytics data
        
    Raises:
        ValueError: If data format is invalid
    """
    if len(binary_data) < 9:
        raise ValueError("Invalid protobuf data: too short")
    
    # Verify header
    if binary_data[:4] != b'WKXP':
        raise ValueError("Invalid protobuf data: bad header")
    
    # Check version (current WorkXplorer protobuf version is 3)
    version = binary_data[4]
    if version != WORKXPLORER_PROTOBUF_VERSION:
        raise ValueError(f"Unsupported protobuf version: {version}, expected: {WORKXPLORER_PROTOBUF_VERSION}")
    
    # Get data length
    length = int.from_bytes(binary_data[5:9], byteorder='little')
    
    # Extract protobuf binary data
    protobuf_data = binary_data[9:9+length]
    
    # Decode using protobuf wire format (implementation required)
    return decode_protobuf_wire_format(protobuf_data)

# Example usage
def webhook_handler(request):
    try:
        analytics_data = decode_workxplorer_protobuf(request.body)
        # Process data...
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}
```

### Node.js Implementation
```javascript
const express = require('express');

// Current WorkXplorer protobuf version
const WORKXPLORER_PROTOBUF_VERSION = 3;

function decodeWorkXplorerProtobuf(binaryData) {
    if (binaryData.length < 9) {
        throw new Error('Invalid protobuf data: too short');
    }
    
    // Verify header
    const header = binaryData.slice(0, 4).toString();
    if (header !== 'WKXP') {
        throw new Error('Invalid protobuf data: bad header');
    }
    
    // Check version (current WorkXplorer protobuf version is 3)
    const version = binaryData[4];
    if (version !== WORKXPLORER_PROTOBUF_VERSION) {
        throw new Error(`Unsupported protobuf version: ${version}, expected: ${WORKXPLORER_PROTOBUF_VERSION}`);
    }
    
    // Get data length (little-endian)
    const length = binaryData.readUInt32LE(5);
    
    // Extract protobuf binary data
    const protobufData = binaryData.slice(9, 9 + length);
    
    // Decode using protobuf library (e.g., protobufjs)
    return decodeProtobufWireFormat(protobufData);
}

// Express.js webhook handler
app.post('/api/analytics', express.raw({type: 'application/x-protobuf'}), (req, res) => {
    try {
        const analyticsData = decodeWorkXplorerProtobuf(req.body);
        
        console.log(`Received data for: ${analyticsData.edupartner_name}`);
        console.log(`Faculty: ${analyticsData.faculty_name || 'N/A'}`);
        
        // Process the analytics data
        processAnalyticsData(analyticsData);
        
        res.json({status: 'success'});
    } catch (error) {
        console.error('Protobuf decode error:', error);
        res.status(400).json({error: error.message});
    }
});
```

### PHP Implementation
```php
<?php

// Current WorkXplorer protobuf version
define('WORKXPLORER_PROTOBUF_VERSION', 3);

function decodeWorkXplorerProtobuf($binaryData) {
    if (strlen($binaryData) < 9) {
        throw new Exception('Invalid protobuf data: too short');
    }
    
    // Verify header
    $header = substr($binaryData, 0, 4);
    if ($header !== 'WKXP') {
        throw new Exception('Invalid protobuf data: bad header');
    }
    
    // Check version (current WorkXplorer protobuf version is 3)
    $version = ord($binaryData[4]);
    if ($version !== WORKXPLORER_PROTOBUF_VERSION) {
        throw new Exception("Unsupported protobuf version: $version, expected: " . WORKXPLORER_PROTOBUF_VERSION);
    }
    
    // Get data length (little-endian)
    $lengthBytes = substr($binaryData, 5, 4);
    $length = unpack('V', $lengthBytes)[1];
    
    // Extract protobuf binary data
    $protobufData = substr($binaryData, 9, $length);
    
    // Decode using protobuf library (e.g., Google's PHP protobuf library)
    return decodeProtobufWireFormat($protobufData);
}

// Webhook handler
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    try {
        $binaryData = file_get_contents('php://input');
        $analyticsData = decodeWorkXplorerProtobuf($binaryData);
        
        echo "Received data for: " . $analyticsData['edupartner_name'] . "\n";
        echo "Faculty: " . ($analyticsData['faculty_name'] ?? 'N/A') . "\n";
        
        // Process analytics data
        processAnalyticsData($analyticsData);
        
        http_response_code(200);
        echo json_encode(['status' => 'success']);
        
    } catch (Exception $e) {
        http_response_code(400);
        echo json_encode(['error' => $e->getMessage()]);
    }
}
?>
```

## Data Structure Reference

### Top-Level Fields
```json
{
    "edupartner_id": "uuid-string",
    "edupartner_name": "University Name",
    "faculty_id": "uuid-string",
    "faculty_name": "Faculty Name", 
    "faculty_domain": "Domain Name",
    "cards": {...},
    "popular_industries": [...],
    "employed_graduates": {...},
    "hiring_funnel": {...},
    "top_companies_by_placements": [...],
    "students_data": {...},
    "timestamp": "2023-12-18T12:14:14.407Z"
}
```

### Cards Structure
```json
"cards": {
    "average_graduate_salary": {
        "value": 0,
        "currency": "UZS",
        "label": "Ср.время зарплата выпускников"
    },
    "students_on_internships": {
        "value": 15,
        "label": "Кол-во студентов на стажировках"
    },
    "average_response_time": {
        "value": 3600.5,
        "unit": "seconds",
        "label": "Ср.вр. отклика работодателей"
    },
    "total_vacancies_offered": {
        "value": 42,
        "label": "Кол-во предложенных вакансий"
    }
}
```

### Popular Industries Structure
```json
"popular_industries": [
    {
        "domain_id": "uuid",
        "domain_name": "Software Development",
        "daily_data": [
            {"date": "2023-12-18", "positions": 5},
            {"date": "2023-12-19", "positions": 8}
        ],
        "monthly_data": [
            {"month": "2023-12", "month_name": "Dec", "positions": 150}
        ]
    }
]
```

### Students Data Structure
```json
"students_data": {
    "total_students": 250,
    "online_students": 45,
    "students_by_faculty": {
        "Computer Science": 120,
        "Mathematics": 80,
        "Physics": 50
    },
    "students_list": [
        {
            "student_id": "uuid",
            "email": "student@example.com",
            "full_name": "John Doe",
            "faculty_name": "Computer Science",
            "is_online": true,
            "last_login": "2023-12-18T11:30:00Z",
            "education_json": "{...}"
        }
    ]
}
```

## Testing Decoding

### Test Data Generator
```python
def generate_test_protobuf_data():
    """Generate test protobuf data for testing decoders."""
    test_data = {
        "edupartner_id": "test-uuid-123",
        "edupartner_name": "Test University",
        "faculty_id": "faculty-uuid-456", 
        "faculty_name": "Computer Science",
        "faculty_domain": "Technology",
        "cards": {
            "students_on_internships": {"value": 10, "label": "Interns"},
            "total_vacancies_offered": {"value": 25, "label": "Jobs"}
        },
        "popular_industries": [],
        "employed_graduates": {"total_graduates": 100, "employed_count": 85},
        "hiring_funnel": {"resumes_created": 200, "hired": 50},
        "top_companies_by_placements": [],
        "students_data": {"total_students": 150, "online_students": 30},
        "timestamp": "2023-12-18T12:00:00Z"
    }
    
    from apps.edupartners.services.protobuf_service import EduPartnerAnalyticsProtobufService
    return EduPartnerAnalyticsProtobufService.encode_analytics_data(test_data)

# Test decoding
binary_test = generate_test_protobuf_data()
decoded = decode_workxplorer_protobuf(binary_test)
print(f"Test successful: {decoded['edupartner_name']}")
```

### Validation Function
```python
def validate_decoded_analytics(data: dict) -> bool:
    """Validate decoded analytics data structure."""
    required_fields = [
        'edupartner_id', 'edupartner_name', 'cards',
        'popular_industries', 'employed_graduates', 
        'hiring_funnel', 'students_data', 'timestamp'
    ]
    
    for field in required_fields:
        if field not in data:
            print(f"Missing required field: {field}")
            return False
    
    # Validate cards
    if not isinstance(data['cards'], dict):
        print("Cards must be a dictionary")
        return False
    
    # Validate students_data 
    students_data = data['students_data']
    if not isinstance(students_data.get('total_students'), int):
        print("total_students must be integer")
        return False
        
    return True
```

## Performance Considerations

### Decoding Performance
- **Binary Size**: Typically 15-30% smaller than JSON
- **Decoding Speed**: Fast due to simple binary format
- **Memory Usage**: Efficient with minimal overhead

### Error Handling
```python
def robust_decode(binary_data: bytes) -> dict:
    """Robust decoder with comprehensive error handling."""
    try:
        return decode_workxplorer_protobuf(binary_data)
    except ValueError as e:
        # Format validation errors
        logger.error(f"Protobuf format error: {e}")
        raise
    except json.JSONDecodeError as e:
        # JSON parsing errors
        logger.error(f"JSON decode error: {e}")
        raise
    except Exception as e:
        # General errors
        logger.error(f"Unexpected decode error: {e}")
        raise
```

## Migration Notes

### Backward Compatibility
If you need to support both JSON and protobuf formats:

```python
def handle_analytics_webhook(request):
    content_type = request.headers.get('Content-Type', '')
    
    if content_type == 'application/x-protobuf':
        # Decode protobuf
        data = decode_workxplorer_protobuf(request.body)
    elif content_type == 'application/json':
        # Decode JSON
        data = request.json()
    else:
        raise ValueError(f"Unsupported content type: {content_type}")
    
    return process_analytics_data(data)
```

This protobuf implementation provides efficient, reliable data transmission while maintaining compatibility and ease of integration for receiving services.