from django.test import SimpleTestCase, TestCase

from registry.health import health_status


class HealthStatusTests(SimpleTestCase):
    def test_reports_ok(self):
        self.assertEqual(health_status(), "ok")


class HealthEndpointTests(TestCase):
    def test_get_returns_ok(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
