# exceptions — idempotency-specific errors


class IdempotencyError(Exception):
    pass


class IdempotencyKeyMissingError(IdempotencyError):
    pass


class KeyConflictError(IdempotencyError):
    pass


class BackendError(IdempotencyError):
    pass


class ConfigurationError(IdempotencyError):
    pass
