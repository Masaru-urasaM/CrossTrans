"""
Quota Manager for CrossTrans Trial Mode.

Manages daily translation quota for users without API keys.
Uses hardware-based device ID for tracking.
"""
import os
import uuid
import hashlib
import logging
from datetime import date
from typing import Optional


class QuotaManager:
    """Manages trial mode quota tracking per device."""

    DAILY_LIMIT = 100  # Maximum translations per day in trial mode

    def __init__(self, config):
        """Initialize QuotaManager.

        Args:
            config: ConfigManager instance for persistent storage.
        """
        self.config = config
        self._device_id: Optional[str] = None

    @property
    def device_id(self) -> str:
        """Get or create unique device ID."""
        if self._device_id is None:
            self._device_id = self._get_or_create_device_id()
        return self._device_id

    def _get_or_create_device_id(self) -> str:
        """Get existing device ID or create a new one.

        Uses hardware-based identification (MAC address + username hash)
        for persistence across reinstalls.
        """
        # Check if device_id already exists in config
        existing_id = self.config.get('device_id')
        if existing_id:
            return existing_id

        # Generate new device ID
        device_id = self._generate_device_id()

        # Save to config
        self.config.set('device_id', device_id)

        logging.info(f"Generated new device ID: {device_id[:8]}...")
        return device_id

    def _generate_device_id(self) -> str:
        """Generate a unique device ID based on hardware identifiers.

        Combines:
        - MAC address (uuid.getnode())
        - Windows username and domain
        - A random component for additional uniqueness
        """
        try:
            # Get MAC address-based identifier
            mac_id = str(uuid.getnode())

            # Get user identifier
            username = os.environ.get('USERNAME', 'unknown')
            domain = os.environ.get('USERDOMAIN', 'local')
            user_id = f"{domain}\\{username}"

            # Combine identifiers
            combined = f"{mac_id}:{user_id}:{uuid.uuid4().hex[:8]}"

            # Hash to create fixed-length ID
            device_id = hashlib.sha256(combined.encode()).hexdigest()[:32]

            return device_id
        except Exception as e:
            logging.warning(f"Failed to generate hardware-based ID: {e}")
            # Fallback to pure random UUID
            return uuid.uuid4().hex[:32]

    def get_quota_info(self) -> dict:
        """Get current quota information.

        Returns:
            dict: {
                'daily_limit': int,
                'used_today': int,
                'remaining': int,
                'reset_date': str (YYYY-MM-DD),
                'is_exhausted': bool
            }
        """
        quota = self._get_or_create_quota()
        today = date.today().isoformat()

        # Check if quota needs reset (new day)
        if quota.get('reset_date') != today:
            quota = self._reset_quota()

        remaining = max(0, self.DAILY_LIMIT - quota.get('used_today', 0))

        return {
            'daily_limit': self.DAILY_LIMIT,
            'used_today': quota.get('used_today', 0),
            'remaining': remaining,
            'reset_date': quota.get('reset_date', today),
            'is_exhausted': remaining <= 0
        }

    def get_remaining_quota(self) -> int:
        """Get remaining translations for today.

        Returns:
            int: Number of remaining translations.
        """
        return self.get_quota_info()['remaining']

    def use_quota(self, count: int = 1) -> bool:
        """Use quota for a translation.

        Args:
            count: Number of quota units to use (default: 1).

        Returns:
            bool: True if quota was available and used, False if exhausted.
        """
        quota_info = self.get_quota_info()

        if quota_info['remaining'] < count:
            logging.warning(f"Trial quota exhausted. Used: {quota_info['used_today']}/{self.DAILY_LIMIT}")
            return False

        # Update quota
        quota = self._get_or_create_quota()
        quota['used_today'] = quota.get('used_today', 0) + count
        self.config.set('trial_quota', quota)

        logging.debug(f"Trial quota used: {quota['used_today']}/{self.DAILY_LIMIT}")
        return True

    def is_quota_available(self) -> bool:
        """Check if quota is available for use.

        Returns:
            bool: True if quota is available, False if exhausted.
        """
        return self.get_remaining_quota() > 0

    def _get_or_create_quota(self) -> dict:
        """Get existing quota data or create default."""
        quota = self.config.get('trial_quota')

        if not quota or not isinstance(quota, dict):
            quota = self._create_default_quota()
            self.config.set('trial_quota', quota)

        return quota

    def _create_default_quota(self) -> dict:
        """Create default quota structure."""
        return {
            'daily_limit': self.DAILY_LIMIT,
            'used_today': 0,
            'reset_date': date.today().isoformat(),
            'device_id': self.device_id,
            'first_use_date': date.today().isoformat()
        }

    def _reset_quota(self) -> dict:
        """Reset quota for a new day."""
        quota = {
            'daily_limit': self.DAILY_LIMIT,
            'used_today': 0,
            'reset_date': date.today().isoformat(),
            'device_id': self.device_id,
            'first_use_date': self.config.get('trial_quota', {}).get(
                'first_use_date', date.today().isoformat()
            )
        }
        self.config.set('trial_quota', quota)
        logging.info("Trial quota reset for new day")
        return quota

    def get_quota_message(self) -> str:
        """Get a user-friendly message about quota status.

        Returns:
            str: Message describing current quota status.
        """
        info = self.get_quota_info()

        if info['is_exhausted']:
            return "Trial quota exhausted. Please add your API key to continue."
        else:
            return f"Trial Mode ({info['remaining']}/{info['daily_limit']} left)"

    def get_exhausted_message(self) -> str:
        """Get message when quota is exhausted.

        Returns:
            str: Detailed message for exhausted quota.
        """
        return (
            "Daily trial quota exhausted (100 translations/day).\n\n"
            "To continue translating:\n"
            "1. Open Settings > Guide tab\n"
            "2. Follow instructions to get a free API key\n"
            "3. Paste your key in the API Key tab\n\n"
            "Quota resets at midnight."
        )
