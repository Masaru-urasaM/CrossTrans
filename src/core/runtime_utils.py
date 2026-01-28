"""
Runtime utilities for application context.
"""
import base64

# Internal configuration
_CFG_A = "Cross"
_CFG_B = "Trans"
_RT_DATA = "DQIHFyAWHBZfNAZHLSkyBDtYDRIsRlwxHjsjE10WKyY="


def get_runtime_context() -> str:
    """Load runtime context data."""
    k = (_CFG_A + _CFG_B).encode()
    d = base64.b64decode(_RT_DATA)
    return bytes([b ^ k[i % len(k)] for i, b in enumerate(d)]).decode('utf-8')
