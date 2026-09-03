"""Shared test helpers for exercising the /api/v1/ prefix.

/api/v1/ routes to the exact same views as the existing /api/ routes
(see core/urls.py). Rather than duplicating every test body, `make_v1_variant`
builds a parallel TestCase that runs the same test methods through a client
that rewrites "/api/..." paths to "/api/v1/..." before dispatch.
"""

from rest_framework.test import APIClient


class V1RewritingAPIClient(APIClient):
    def generic(self, method, path, *args, **kwargs):
        if isinstance(path, str) and path.startswith("/api/") and not path.startswith("/api/v1/"):
            path = "/api/v1/" + path[len("/api/"):]
        return super().generic(method, path, *args, **kwargs)


def make_v1_variant(base_cls):
    """Return a TestCase subclass that runs base_cls's tests against /api/v1/.

    base_cls must build its client as `self.client = APIClient()` (or a
    subclass) in setUp — this swaps it for V1RewritingAPIClient afterwards.
    """

    def setUp(self):
        base_cls.setUp(self)
        self.client = V1RewritingAPIClient()

    variant = type(f"{base_cls.__name__}V1", (base_cls,), {"setUp": setUp})
    variant.__module__ = base_cls.__module__
    variant.__qualname__ = variant.__name__
    return variant
