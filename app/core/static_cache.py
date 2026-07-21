"""
StaticFiles mit Cache-Control-Header - Starlettes StaticFiles setzt von sich
aus nur ETag/Last-Modified (ermöglicht 304-Revalidierung), aber kein
Cache-Control, das eine erneute Anfrage an den Server überhaupt erst
überflüssig macht. Jede Revalidierung ist ein zusätzlicher Roundtrip.
"""
from starlette.staticfiles import StaticFiles


class CachedStaticFiles(StaticFiles):
    def __init__(self, *args, cache_control: str, versioned_cache_control: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cache_control = cache_control
        # Optional: alle CSS/JS-Referenzen tragen seit der Production-
        # Readiness-Runde ein Cache-Busting `?v=<App-Version>` (siehe
        # app/core/templating.py::asset_version) - eine URL MIT Query-String
        # kann bedenkenlos ein Jahr lang unveraendert im Browser bleiben
        # (bei einem Release aendert sich die URL selbst). Requests OHNE
        # Version (Manifest, Icons - werden praktisch nie geaendert, aber
        # tragen keine ?v=) bleiben auf der kürzeren, revalidierenden Dauer.
        self._versioned_cache_control = versioned_cache_control or cache_control

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        scope = kwargs.get("scope") or (args[2] if len(args) > 2 else None)
        has_version_query = bool(scope and scope.get("query_string"))
        response.headers["Cache-Control"] = self._versioned_cache_control if has_version_query else self._cache_control
        return response
