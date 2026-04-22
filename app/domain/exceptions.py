"""Domain-specific exceptions."""


class DeviceNotFoundError(Exception):
    """Raised when a requested mock device does not exist."""


class DeviceUnavailableError(Exception):
    """Raised when a device exists but cannot accept configuration changes."""


class InventoryBackendError(Exception):
    """Raised when the selected inventory backend cannot be initialized."""


class AutomationExecutionError(Exception):
    """Raised when a configuration workflow cannot be executed successfully."""
