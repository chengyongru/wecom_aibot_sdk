"""Utility methods"""

import uuid
from typing import Optional


def generate_req_id(prefix: Optional[str] = None) -> str:
    """
    Generate request ID

    Args:
        prefix: Optional prefix, e.g., 'stream'

    Returns:
        String in format 'prefix_uuid' or 'uuid'
    """
    req_id = uuid.uuid4().hex[:16]
    if prefix:
        return f"{prefix}_{req_id}"
    return req_id
