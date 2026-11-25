"""Application error type.

Moved here from app.main in Phase 2 so services can raise AppError
without importing app.main (which would be a circular import: main
imports the routers, routers import the services). main.py imports it
back from here, so behaviour is unchanged.
"""


class AppError(Exception):
    """An error we deliberately raise in services/routes.

    Carries an HTTP status and a safe, user-facing message. Anything that
    is not an AppError is an unexpected bug and becomes a generic 500 —
    internal details are never leaked to the client.
    """

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
