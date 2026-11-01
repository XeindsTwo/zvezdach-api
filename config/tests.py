from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import TechnicalSiteRobotsMiddleware


@override_settings(MEDIA_URL="/media/", STATIC_URL="/static/")
class TechnicalSiteRobotsTests(SimpleTestCase):
    def test_cms_api_errors_and_redirects_are_not_indexed(self):
        factory = RequestFactory()
        for path in ["/", "/cms/login/", "/api/v1/articles/", "/missing", "/media-other"]:
            for status in [200, 302, 404, 500]:
                with self.subTest(path=path, status=status):
                    middleware = TechnicalSiteRobotsMiddleware(lambda request: HttpResponse(status=status))
                    response = middleware(factory.get(path))
                    self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
                    self.assertEqual(response.status_code, status)

    def test_asset_headers_are_unchanged(self):
        for path in ["/media/photo.webp", "/static/cms/style.css"]:
            with self.subTest(path=path):
                middleware = TechnicalSiteRobotsMiddleware(lambda request: HttpResponse(b"asset"))
                response = middleware(RequestFactory().get(path))
                self.assertNotIn("X-Robots-Tag", response)
                self.assertEqual(response.content, b"asset")
