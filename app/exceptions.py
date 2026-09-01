"""Application-specific exceptions."""


class ConfigurationError(Exception):
    """Raised when configuration is invalid at startup (fatal)."""


class RecoverableAutomationError(Exception):
    """Raised for unexpected but recoverable errors during a single cycle."""


class PlatformNotSupportedError(Exception):
    """Raised when required platform APIs are unavailable (fatal at startup)."""
