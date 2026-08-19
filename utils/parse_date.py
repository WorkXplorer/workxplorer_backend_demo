from datetime import date, datetime


def parse_date(value):
    """
    Parse date from various formats.
    Handles: date objects, datetime objects, ISO strings, and None/empty strings.
    Returns: date object or None
    """
    if value is None or value == "" or value == "null":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            # Try ISO format first (YYYY-MM-DD)
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            try:
                # Try datetime format with time
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            except ValueError:
                return None
    return None
