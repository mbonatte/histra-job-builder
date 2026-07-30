class BuilderError(Exception):
    """Base exception raised by the builder."""


class InvalidJobError(BuilderError):
    """The JOB cannot be compiled."""


class TemplateNotFoundError(BuilderError):
    """The requested immutable template does not exist."""


class TemplateIntegrityError(BuilderError):
    """The template content does not match its declared digest."""


class PatchError(BuilderError):
    """An XML patch could not be applied unambiguously."""
