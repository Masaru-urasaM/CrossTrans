"""
Trial Mode API Handler for CrossTrans.

Handles API requests for trial mode users via a proxy server.
The proxy protects the developer's API key while providing
limited free access to new users.
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from src.constants import (
    TRIAL_PROXY_URL,
    TRIAL_MODEL,
    TRIAL_PROVIDER,
    TRIAL_MODE_ENABLED
)


class TrialAPIError(Exception):
    """Exception raised for trial API errors."""
    pass


class TrialAPIClient:
    """Client for making trial mode API requests via proxy."""

    # Timeout for API requests (seconds)
    REQUEST_TIMEOUT = 30

    def __init__(self, device_id: str):
        """Initialize TrialAPIClient.

        Args:
            device_id: Unique device identifier for quota tracking.
        """
        self.device_id = device_id
        self.proxy_url = TRIAL_PROXY_URL
        self.model = TRIAL_MODEL
        self.provider = TRIAL_PROVIDER

    def is_available(self) -> bool:
        """Check if trial mode is available.

        Returns:
            bool: True if trial mode is configured and enabled.
        """
        return bool(TRIAL_MODE_ENABLED and self.proxy_url)

    def translate(self, prompt: str) -> str:
        """Translate text using trial mode API.

        Args:
            prompt: The translation prompt (includes source text and target language).

        Returns:
            str: Translated text.

        Raises:
            TrialAPIError: If the request fails.
        """
        if not self.is_available():
            raise TrialAPIError(
                "Trial mode is not configured. "
                "Please add your own API key in Settings."
            )

        try:
            return self._make_request(prompt)
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode('utf-8')
            except Exception:
                pass

            if e.code == 429:
                raise TrialAPIError(
                    "Trial service is currently busy. Please try again in a moment."
                )
            elif e.code == 403:
                raise TrialAPIError(
                    "Trial quota exceeded or access denied. "
                    "Please add your own API key to continue."
                )
            elif e.code == 401:
                raise TrialAPIError(
                    "Trial service authentication error. "
                    "Please add your own API key."
                )
            else:
                logging.error(f"Trial API HTTP error {e.code}: {error_body}")
                raise TrialAPIError(f"Trial service error (HTTP {e.code})")

        except urllib.error.URLError as e:
            logging.error(f"Trial API URL error: {e}")
            raise TrialAPIError(
                "Cannot connect to trial service. "
                "Please check your internet connection or add your own API key."
            )
        except json.JSONDecodeError as e:
            logging.error(f"Trial API JSON decode error: {e}")
            raise TrialAPIError("Invalid response from trial service.")
        except Exception as e:
            logging.error(f"Trial API unexpected error: {e}")
            raise TrialAPIError(f"Trial service error: {str(e)}")

    def _make_request(self, prompt: str) -> str:
        """Make HTTP request to proxy server.

        Args:
            prompt: Translation prompt.

        Returns:
            str: Response content.
        """
        # Build request payload
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4096
        }

        # Build headers
        headers = {
            "Content-Type": "application/json",
            "X-Device-ID": self.device_id,
            "User-Agent": "CrossTrans-Trial/1.0"
        }

        # Encode payload
        data = json.dumps(payload).encode('utf-8')

        # Create request
        request = urllib.request.Request(
            self.proxy_url,
            data=data,
            headers=headers,
            method='POST'
        )

        # Make request
        with urllib.request.urlopen(request, timeout=self.REQUEST_TIMEOUT) as response:
            response_data = response.read().decode('utf-8')

            # DEBUG: Log raw response for troubleshooting
            logging.info(f"[Trial] Response status: {response.status}")
            logging.debug(f"[Trial] Raw response (first 500 chars): {response_data[:500]}")

            try:
                result = json.loads(response_data)
            except json.JSONDecodeError as e:
                # Log the raw response to help diagnose the issue
                logging.error(f"[Trial] JSON decode failed. Raw response: {response_data[:1000]}")
                raise

        # Parse response (OpenAI-compatible format)
        return self._parse_response(result)

    def _parse_response(self, result: dict) -> str:
        """Parse API response.

        Args:
            result: JSON response from API.

        Returns:
            str: Extracted content.

        Raises:
            TrialAPIError: If response format is unexpected.
        """
        try:
            # Standard OpenAI-compatible response format
            if 'choices' in result:
                return result['choices'][0]['message']['content'].strip()

            # Alternative format (direct content)
            if 'content' in result:
                return result['content'].strip()

            # Error response
            if 'error' in result:
                error_msg = result['error'].get('message', str(result['error']))
                raise TrialAPIError(f"API Error: {error_msg}")

            raise TrialAPIError("Unexpected response format from trial service.")

        except (KeyError, IndexError) as e:
            logging.error(f"Failed to parse trial API response: {e}")
            raise TrialAPIError("Failed to parse trial service response.")


def create_trial_client(device_id: str) -> Optional[TrialAPIClient]:
    """Factory function to create TrialAPIClient if available.

    Args:
        device_id: Device identifier for quota tracking.

    Returns:
        TrialAPIClient if trial mode is enabled, None otherwise.
    """
    if TRIAL_MODE_ENABLED and TRIAL_PROXY_URL:
        return TrialAPIClient(device_id)
    return None
