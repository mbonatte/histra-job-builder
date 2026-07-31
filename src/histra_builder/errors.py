class BuilderError(Exception):
    """Base class for expected builder errors."""

class InvalidJobError(BuilderError):
    pass

class InvalidHrxError(BuilderError):
    pass

class PatchError(BuilderError):
    pass

class TemplateNotFoundError(BuilderError):
    pass

class TemplateIntegrityError(BuilderError):
    pass

class VariantError(BuilderError):
    pass
