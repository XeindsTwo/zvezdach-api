from urllib.parse import urlsplit

from django.conf import settings


class TechnicalSiteRobotsMiddleware:
    """Keep CMS/API responses out of search without excluding public media."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        asset_paths = [urlsplit(settings.MEDIA_URL).path, urlsplit(settings.STATIC_URL).path]
        is_asset = any(
            prefix and prefix != "/" and (
                request.path_info == prefix.rstrip("/")
                or request.path_info.startswith(prefix.rstrip("/") + "/")
            )
            for prefix in asset_paths
        )
        if not is_asset:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
