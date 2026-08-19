import os
import threading
import time
import uuid
from django.db import models

_v7_lock = threading.Lock()
_v7_last_ms = 0
_v7_counter = 0

def uuidv7() -> uuid.UUID:
    """Generate a UUIDv7, monotonic within this process (RFC 9562, Method 1)."""
    global _v7_last_ms, _v7_counter

    value = bytearray(os.urandom(16))

    with _v7_lock:
        timestamp = int(time.time() * 1000)
        if timestamp <= _v7_last_ms:
            # Same millisecond (or clock went backwards): bump the counter
            # and keep the previous timestamp so ordering is preserved.
            timestamp = _v7_last_ms
            _v7_counter += 1
            if _v7_counter > 0x0FFF:  # 12-bit counter overflowed
                _v7_counter = 0
                timestamp += 1
                _v7_last_ms = timestamp
        else:
            _v7_last_ms = timestamp
            _v7_counter = 0
        counter = _v7_counter

    # Timestamp (48 bits)
    value[0] = (timestamp >> 40) & 0xFF
    value[1] = (timestamp >> 32) & 0xFF
    value[2] = (timestamp >> 24) & 0xFF
    value[3] = (timestamp >> 16) & 0xFF
    value[4] = (timestamp >> 8) & 0xFF
    value[5] = timestamp & 0xFF

    # Version (4 bits) + 12-bit monotonic counter instead of random bits
    value[6] = 0x70 | ((counter >> 8) & 0x0F)
    value[7] = counter & 0xFF

    # Variant RFC4122
    value[8] = (value[8] & 0x3F) | 0x80

    return uuid.UUID(bytes=bytes(value))


class UUIDField(models.UUIDField):
    """Custom UUID field supporting multiple versions."""

    def __init__(
            self,
            primary_key: bool = True,
            version: int | None = None,
            editable: bool = False,
            *args,
            **kwargs
    ):
        if version:
            if version == 2:
                raise ValueError("UUID version 2 is not supported.")
            if version not in [1, 4, 7]:
                raise ValueError("Only UUID versions 1, 4, and 7 are supported.")

            version_map = {
                1: uuid.uuid1,
                4: uuid.uuid4,
                7: uuidv7,
            }
            kwargs.setdefault("default", version_map[version])
        else:
            kwargs.setdefault("default", uuid.uuid4)

        kwargs.setdefault("editable", editable)
        kwargs.setdefault("primary_key", primary_key)

        super().__init__(*args, **kwargs)