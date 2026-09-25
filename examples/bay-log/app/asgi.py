"""Service entrypoint: the FastAPI app with the Flask LTI provider mounted.

Run with:  uvicorn app.asgi:app --host 0.0.0.0 --port 8080

The LTI provider stays a separate WSGI app because pylti1p3 ships Flask
and Django integrations only. The two halves share identity through the
app_sessions table rather than a shared cookie secret.
"""

from a2wsgi import WSGIMiddleware

from .main import app

try:
    from .lti_app import flask_app

    app.mount("/lti", WSGIMiddleware(flask_app))
    LTI_MOUNTED = True
except Exception as exc:  # pragma: no cover
    # The tool must still run if LTI isn't configured yet (no keys, no
    # Client ID from Canvas). Canvas wiring is step 2, not a hard
    # dependency of the workflow tool.
    import logging

    logging.getLogger("blendzone").warning("LTI provider not mounted: %s", exc)
    LTI_MOUNTED = False

__all__ = ["app", "LTI_MOUNTED"]
