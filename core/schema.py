"""
Custom drf-spectacular schema extensions that wrap all API responses
in the WorkXplorer standardized format used by StandardJSONRenderer.

Success format:
{
    "success": true,
    "message": "...",
    "data": {...},
    "timestamp": "..."
}

Paginated format:
{
    "success": true,
    "message": "...",
    "data": [...],
    "pagination": {"count": ..., "next": ..., "previous": ...},
    "timestamp": "..."
}

Error format:
{
    "success": false,
    "error": {"code": "...", "message": "...", "details": ...},
    "timestamp": "..."
}
"""

def postprocess_schema_responses(result, generator, request, public):
    """
    drf-spectacular postprocessing hook that wraps all response schemas
    in the WorkXplorer standardized response envelope.
    """
    # Define reusable components
    error_schema = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "example": False},
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "example": "BAD_REQUEST"},
                    "message": {"type": "string", "example": "An error occurred"},
                    "details": {},
                    "field_errors": {"type": "object"},
                },
                "required": ["code", "message"],
            },
            "timestamp": {
                "type": "string",
                "format": "date-time",
                "example": "2026-02-24T10:00:00+00:00",
            },
        },
        "required": ["success", "error", "timestamp"],
    }

    pagination_schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "next": {"type": "integer", "nullable": True},
            "previous": {"type": "integer", "nullable": True},
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
        },
    }

    # Add reusable error components
    if "components" not in result:
        result["components"] = {}
    if "schemas" not in result["components"]:
        result["components"]["schemas"] = {}

    result["components"]["schemas"]["StandardErrorResponse"] = error_schema
    result["components"]["schemas"]["PaginationInfo"] = pagination_schema

    paths = result.get("paths", {})
    for path_url, path_item in paths.items():
        for method, operation in path_item.items():
            if method in ("get", "post", "put", "patch", "delete", "options", "head"):
                responses = operation.get("responses", {})
                new_responses = {}

                for status_code, response_obj in responses.items():
                    code = int(status_code) if status_code.isdigit() else 200

                    if code >= 400:
                        # Error responses
                        new_responses[status_code] = {
                            "description": response_obj.get("description", "Error"),
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/StandardErrorResponse"
                                    }
                                }
                            },
                        }
                        continue

                    content = response_obj.get("content", {})
                    json_content = content.get("application/json", {})
                    original_schema = json_content.get("schema", {})

                    if not original_schema and code == 204:
                        # 204 No Content - wrap in success
                        new_responses["200"] = {
                            "description": response_obj.get(
                                "description", "Success"
                            ),
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {
                                                "type": "boolean",
                                                "example": True,
                                            },
                                            "message": {
                                                "type": "string",
                                                "example": "Operation completed successfully",
                                            },
                                            "data": original_schema
                                            if original_schema
                                            else {"type": "object", "nullable": True},
                                            "timestamp": {
                                                "type": "string",
                                                "format": "date-time",
                                                "example": "2026-02-24T10:00:00+00:00",
                                            },
                                        },
                                        "required": [
                                            "success",
                                            "message",
                                            "timestamp",
                                        ],
                                    }
                                }
                            },
                        }
                        continue

                    if not original_schema:
                        new_responses[status_code] = response_obj
                        continue

                    # Detect if this is a paginated response
                    is_paginated = False
                    if original_schema.get("type") == "object":
                        props = original_schema.get("properties", {})
                        if "results" in props and "count" in props:
                            is_paginated = True

                    # Also check if it's a $ref that resolves to a paginated schema
                    ref = original_schema.get("$ref", "")
                    if ref:
                        ref_name = ref.split("/")[-1]
                        ref_schema = (
                            result.get("components", {})
                            .get("schemas", {})
                            .get(ref_name, {})
                        )
                        if ref_schema.get("type") == "object":
                            ref_props = ref_schema.get("properties", {})
                            if "results" in ref_props and "count" in ref_props:
                                is_paginated = True

                    if is_paginated:
                        # Extract the results schema from the paginated response.
                        if ref:
                            ref_name = ref.split("/")[-1]
                            ref_schema = (
                                result.get("components", {})
                                .get("schemas", {})
                                .get(ref_name, {})
                            )
                            resolved_schema = ref_schema
                        else:
                            resolved_schema = original_schema

                        results_schema = (
                            resolved_schema.get("properties", {})
                            .get("results", {})
                        )

                        if results_schema.get("type") == "array":
                            data_schema = {
                                "type": "array",
                                "items": (
                                    results_schema.get("items", {})
                                ),
                            }
                            pagination_schema_ref = {
                                "$ref": "#/components/schemas/PaginationInfo"
                            }
                        else:
                            data_schema = results_schema if results_schema else {}
                            pagination_schema_ref = {
                                "type": "object",
                                "properties": {
                                    "count": (
                                        resolved_schema.get("properties", {})
                                        .get("count", {"type": "integer"})
                                    ),
                                    "next": (
                                        resolved_schema.get("properties", {})
                                        .get(
                                            "next",
                                            {"type": "string", "nullable": True},
                                        )
                                    ),
                                    "previous": (
                                        resolved_schema.get("properties", {})
                                        .get(
                                            "previous",
                                            {"type": "string", "nullable": True},
                                        )
                                    ),
                                    "limit": (
                                        resolved_schema.get("properties", {})
                                        .get("limit", {"type": "integer"})
                                    ),
                                    "offset": (
                                        resolved_schema.get("properties", {})
                                        .get("offset", {"type": "integer"})
                                    ),
                                },
                            }

                        wrapped = {
                            "type": "object",
                            "properties": {
                                "success": {
                                    "type": "boolean",
                                    "example": True,
                                },
                                "message": {
                                    "type": "string",
                                    "example": "Data retrieved successfully",
                                },
                                "data": data_schema,
                                "pagination": pagination_schema_ref,
                                "timestamp": {
                                    "type": "string",
                                    "format": "date-time",
                                    "example": "2026-02-24T10:00:00+00:00",
                                },
                            },
                            "required": [
                                "success",
                                "message",
                                "data",
                                "pagination",
                                "timestamp",
                            ],
                        }
                    else:
                        # Non-paginated success response
                        message_example = "Operation completed successfully"
                        if code == 201:
                            message_example = "Resource created successfully"

                        wrapped = {
                            "type": "object",
                            "properties": {
                                "success": {
                                    "type": "boolean",
                                    "example": True,
                                },
                                "message": {
                                    "type": "string",
                                    "example": message_example,
                                },
                                "data": original_schema,
                                "timestamp": {
                                    "type": "string",
                                    "format": "date-time",
                                    "example": "2026-02-24T10:00:00+00:00",
                                },
                            },
                            "required": ["success", "message", "data", "timestamp"],
                        }

                    new_responses[status_code] = {
                        "description": response_obj.get("description", "Success"),
                        "content": {
                            "application/json": {"schema": wrapped}
                        },
                    }

                # Add standard error responses if not present
                if "401" not in new_responses:
                    new_responses["401"] = {
                        "description": "Unauthorized",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/StandardErrorResponse"
                                }
                            }
                        },
                    }

                operation["responses"] = new_responses

    return result
