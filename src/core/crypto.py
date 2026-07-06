"""
Secure storage for API keys using Windows DPAPI.
Data Protection API (DPAPI) encrypts data so only the same Windows user can decrypt it.
"""
import base64
import logging
from typing import Optional

# Try to import Windows DPAPI
try:
    import win32crypt
    HAS_DPAPI = True
except ImportError:
    HAS_DPAPI = False
    logging.warning("win32crypt not available - falling back to plaintext storage")


class SecureStorage:
    """Encrypt/decrypt sensitive data using Windows DPAPI.

    DPAPI ties encryption to the current Windows user account.
    Data encrypted on one machine/user cannot be decrypted by another.

    Usage:
        encrypted = SecureStorage.encrypt("my-api-key")
        decrypted = SecureStorage.decrypt(encrypted)
    """

    # Application-specific entropy adds extra layer of protection
    ENTROPY: bytes = b"CrossTrans_v1.6_SecureKey"
    DESCRIPTION: str = "CrossTrans API Key"

    @classmethod
    def encrypt(cls, plaintext: str) -> Optional[str]:
        """Encrypt string using DPAPI, return base64-encoded ciphertext.

        Args:
            plaintext: The sensitive string to encrypt (e.g., API key)

        Returns:
            Base64-encoded encrypted string, or None if encryption failed
        """
        if not HAS_DPAPI:
            logging.warning("DPAPI not available, cannot encrypt")
            return None

        if not plaintext:
            return None

        try:
            # CryptProtectData returns encrypted bytes
            encrypted = win32crypt.CryptProtectData(
                plaintext.encode('utf-8'),  # Data to encrypt
                cls.DESCRIPTION,             # Description (visible in memory dumps)
                cls.ENTROPY,                 # Optional entropy
                None,                        # Reserved
                None,                        # PromptStruct (no UI prompt)
                0                            # Flags
            )
            # Return as base64 for JSON storage
            return base64.b64encode(encrypted).decode('ascii')
        except Exception as e:
            logging.error(f"DPAPI encryption failed: {e}")
            return None

    @classmethod
    def decrypt(cls, ciphertext: str) -> Optional[str]:
        """Decrypt base64-encoded DPAPI ciphertext.

        Args:
            ciphertext: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string, or None if decryption failed
        """
        if not HAS_DPAPI:
            logging.warning("DPAPI not available, cannot decrypt")
            return None

        if not ciphertext:
            return None

        try:
            # Decode base64 to get encrypted bytes
            encrypted = base64.b64decode(ciphertext)

            # CryptUnprotectData returns (description, decrypted_data)
            _, decrypted = win32crypt.CryptUnprotectData(
                encrypted,      # Encrypted data
                cls.ENTROPY,    # Must match encryption entropy
                None,           # Reserved
                None,           # PromptStruct
                0               # Flags
            )
            return decrypted.decode('utf-8')
        except Exception as e:
            logging.error(f"DPAPI decryption failed: {e}")
            return None

    @classmethod
    def is_available(cls) -> bool:
        """Check if DPAPI is available on this system."""
        return HAS_DPAPI

    @classmethod
    def is_encrypted(cls, value: str) -> bool:
        """Check if a string appears to be DPAPI encrypted (base64).

        Heuristic: DPAPI encrypted data is base64, typically longer than
        the original and starts with certain patterns.
        """
        if not value or len(value) < 20:
            return False

        try:
            # Try to decode as base64
            decoded = base64.b64decode(value)
            # DPAPI encrypted data typically starts with specific bytes
            # Check if it looks like valid DPAPI blob
            return len(decoded) > 50  # Encrypted data is much larger
        except Exception:
            return False
