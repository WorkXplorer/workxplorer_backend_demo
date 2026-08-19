"""
Currency rate fetching from the Central Bank of Uzbekistan.

Fetches daily exchange rates for USD, RUB, EUR and saves them as JSON files
in the general/currency/ directory. Scheduled to run daily at 02:00 AM.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# Directory where currency JSON files are stored
CURRENCY_DIR = Path(__file__).parent

# CBU API base URL
CBU_API_BASE = "https://cbu.uz/uz/arkhiv-kursov-valyut/json"

# Supported currencies
SUPPORTED_CURRENCIES = ("USD", "RUB", "EUR")


def fetch_currency_rate(currency_code: str) -> Optional[dict]:
    """
    Fetch the current exchange rate for a currency from the Central Bank of Uzbekistan.

    Args:
        currency_code: One of 'USD', 'RUB', 'EUR'

    Returns:
        Parsed JSON response from CBU API, or None on failure.
    """
    url = f"{CBU_API_BASE}/{currency_code}/"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list):
            return data
        logger.warning("Unexpected response format from CBU API for %s: %s", currency_code, type(data))
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch %s rate from CBU: %s", currency_code, e)
        return None
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse CBU response for %s: %s", currency_code, e)
        return None


def save_currency_data(currency_code: str, data: list) -> bool:
    """
    Save currency data to a JSON file.

    Args:
        currency_code: Currency code (e.g., 'USD')
        data: List of rate data from CBU API

    Returns:
        True if saved successfully, False otherwise.
    """
    file_path = CURRENCY_DIR / f"{currency_code}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Saved %s rate data to %s", currency_code, file_path)
        return True
    except (OSError, IOError) as e:
        logger.error("Failed to save %s rate data: %s", currency_code, e)
        return False


def load_currency_data(currency_code: str) -> Optional[list]:
    """
    Load currency data from the saved JSON file.

    Args:
        currency_code: Currency code (e.g., 'USD')

    Returns:
        Parsed JSON data or None if file doesn't exist or is invalid.
    """
    file_path = CURRENCY_DIR / f"{currency_code}.json"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Currency file not found: %s", file_path)
        return None
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to load currency data for %s: %s", currency_code, e)
        return None


def get_rate_to_uzs(currency_code: str) -> Optional[float]:
    """
    Get the exchange rate of 1 unit of the given currency in UZS.

    For UZS, returns 1.0.
    For others, reads from saved JSON files and extracts the Rate field.
    If the file is missing, attempts to fetch from CBU API first.

    Args:
        currency_code: Currency code (USD, EUR, RUB, UZS)

    Returns:
        Exchange rate as float, or None if unavailable.
    """
    currency_code = currency_code.upper().strip()

    if currency_code == "UZS":
        return 1.0

    if currency_code not in SUPPORTED_CURRENCIES:
        logger.warning("Unsupported currency: %s", currency_code)
        return None

    data = load_currency_data(currency_code)

    # If no saved data, try fetching from CBU
    if not data:
        logger.info("No cached rate for %s, fetching from CBU...", currency_code)
        data = fetch_currency_rate(currency_code)
        if data:
            save_currency_data(currency_code, data)

    if not data or not isinstance(data, list) or len(data) == 0:
        return None

    try:
        # CBU returns a list with one element containing "Rate" field
        rate_str = data[0].get("Rate")
        if rate_str is None:
            logger.error("No 'Rate' field in CBU data for %s", currency_code)
            return None
        # Rate is a string like "12850.45" — replace comma with dot if needed
        rate = float(str(rate_str).replace(",", "."))
        return rate
    except (ValueError, TypeError, IndexError) as e:
        logger.error("Failed to parse rate for %s: %s", currency_code, e)
        return None


def update_all_currency_rates() -> dict:
    """
    Fetch and save exchange rates for all supported currencies.
    Called by the scheduler daily at 02:00 AM.

    Returns:
        Dict with status per currency.
    """
    results = {}
    for currency_code in SUPPORTED_CURRENCIES:
        data = fetch_currency_rate(currency_code)
        if data:
            saved = save_currency_data(currency_code, data)
            results[currency_code] = "saved" if saved else "save_failed"
        else:
            results[currency_code] = "fetch_failed"

    logger.info("Currency rate update results: %s", results)
    return results
