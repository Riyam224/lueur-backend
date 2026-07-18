from whitenoise.storage import CompressedManifestStaticFilesStorage


class LenientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Falls back to the unhashed path instead of raising a 500 if collectstatic
    didn't run (or ran incompletely) before deploy."""

    manifest_strict = False
