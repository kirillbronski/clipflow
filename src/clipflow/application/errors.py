"""Queue rule violations carry a stable code; callers never parse the message."""

RULE_CODES = frozenset(
    {
        'scheduler_closed',
        'job_not_startable',
        'source_required',
        'job_not_resumable',
        'cooldown_active',
        'job_not_retryable',
        'source_not_expected',
        'source_changed',
        'selection_not_expected',
        'invalid_mode',
        'job_not_repeatable',
    }
)


class JobRuleError(ValueError):
    """A command the job's current state does not allow; still a ``ValueError``."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
