class ProvisioningError(Exception):
    """
    Base exception for all user provisioning failures.
    """

class PersonaNotFoundError(ProvisioningError):
    """
    The external API returned no data for the given indiv_id.
    """

class NoValidEmailError(ProvisioningError):
    """
    Persona data was found but contains no usable email address.
    """

class AccountCreationError(ProvisioningError):
    """
    Django account creation failed, typically due to AccountCreationForm
    validation errors. The form errors are attached as form_errors.
    """
    def __init__(self, message, form_errors=None):
        super().__init__(message)
        self.form_errors = form_errors or {}
