"""
Utility functions for HR analytics calculations.
Provides serialization and helper functions used across analytics modules.
"""

import uuid
import logging
import math
import json
from decimal import Decimal
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


def serialize_value(value: Any) -> Any:
    """
    Recursively serialize values to JSON-compatible format.
    Handles datetime objects, Decimal, UUID, and ensures float values are JSON compliant.
    """
    if value is None:
        return None
    elif isinstance(value, uuid.UUID):
        return str(value)
    elif isinstance(value, (datetime, date, time)):
        return value.isoformat()
    elif isinstance(value, Decimal):
        float_val = float(value)
        if not math.isfinite(float_val):
            return None
        return float_val
    elif isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    elif isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    elif hasattr(value, "isoformat"):
        return value.isoformat()
    elif hasattr(value, "__dict__"):
        if hasattr(value, "pk"):
            return str(value.pk) if value.pk is not None else None
        try:
            return serialize_value(value.__dict__)
        except Exception:
            return str(value)
    else:
        return value


def calculate_percentage_change(current: int, previous: int) -> Optional[float]:
    """
    Calculate percentage change between two values.
    
    Args:
        current: Current period value
        previous: Previous period value
        
    Returns:
        Percentage change as float, or None if previous is 0
    """
    if previous == 0:
        return None
    percentage = ((current - previous) / previous) * 100
    return round(percentage, 1)


def get_period_dates(
        end_date: Optional[datetime] = None,
        period_days: int = 30
) -> Dict[str, datetime]:
    """
    Calculate current and previous period date ranges.
    
    Args:
        end_date: End date of current period (default: now)
        period_days: Length of period in days
        
    Returns:
        Dictionary with current and previous period dates
    """
    if end_date is None:
        end_date = timezone.now()

    start_date = end_date - timedelta(days=period_days)
    previous_end_date = start_date
    previous_start_date = previous_end_date - timedelta(days=period_days)

    return {
        "current_start": start_date,
        "current_end": end_date,
        "previous_start": previous_start_date,
        "previous_end": previous_end_date,
        "period_days": period_days,
    }


def validate_json_payload(payload: dict) -> dict:
    """
    Validate and clean payload to ensure JSON compliance.
    Returns a cleaned version of the payload.
    """
    try:
        json.dumps(payload)
        return payload
    except (TypeError, ValueError) as e:
        logger.warning("JSON validation failed, attempting to clean payload: %s", e)
        return serialize_value(payload)


def base_instance_dict(
        instance: models.Model, extra_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a base dictionary for a model instance containing common fields.
    
    Args:
        instance: Django model instance
        extra_fields: List of attribute names to attempt to include from the instance
        
    Returns:
        Dictionary with serialized model data
    """
    data: Dict[str, Any] = {}
    if hasattr(instance, "id"):
        data["id"] = serialize_value(getattr(instance, "id"))
    if hasattr(instance, "uuid"):
        data["uuid"] = serialize_value(getattr(instance, "uuid"))
    # include both created_at and common applied_at for compatibility
    if hasattr(instance, "created_at"):
        data["created_at"] = serialize_value(getattr(instance, "created_at"))
    if hasattr(instance, "applied_at"):
        data["applied_at"] = serialize_value(getattr(instance, "applied_at"))
    if hasattr(instance, "updated_at"):
        data["updated_at"] = serialize_value(getattr(instance, "updated_at"))

    if extra_fields:
        for field in extra_fields:
            if hasattr(instance, field):
                try:
                    data[field] = serialize_value(getattr(instance, field))
                except Exception:
                    logger.exception(
                        "Failed to serialize field %s for instance %s", field, instance
                    )
    return data


# Backward compatibility aliases
_serialize_value = serialize_value
_base_instance_dict = base_instance_dict
