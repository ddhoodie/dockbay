import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase

from registry.middleware import RequestLoggingMiddleware


class TemporaryRequestLogMixin:
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.log_path = Path(self.directory.name) / "dockbay.log"
        self.logger = logging.getLogger("dockbay.requests")
        self.original_handlers = self.logger.handlers[:]
        self.original_level = self.logger.level
        self.original_propagate = self.logger.propagate

        formatter_config = settings.LOGGING["formatters"]["application"]
        self.handler = logging.FileHandler(self.log_path, encoding="utf-8")
        self.handler.setFormatter(
            logging.Formatter(
                formatter_config["format"],
                datefmt=formatter_config["datefmt"],
                style=formatter_config["style"],
            )
        )
        self.logger.handlers = [self.handler]
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

    def tearDown(self):
        self.handler.close()
        self.logger.handlers = self.original_handlers
        self.logger.setLevel(self.original_level)
        self.logger.propagate = self.original_propagate
        self.directory.cleanup()
        super().tearDown()

    def log_lines(self):
        self.handler.flush()
        return self.log_path.read_text(encoding="utf-8").splitlines()


class RequestLoggingMiddlewareTests(TemporaryRequestLogMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def run_middleware(self, status, path="/health/"):
        response = HttpResponse(status=status)
        middleware = RequestLoggingMiddleware(lambda request: response)
        returned = middleware(self.factory.get(path))
        return response, returned

    def test_200_response_emits_one_info_event_and_returns_original_response(self):
        response, returned = self.run_middleware(200)

        self.assertIs(returned, response)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("INFO dockbay.requests", lines[0])
        self.assertIn("method=GET path=/health/ status=200", lines[0])

    def test_404_response_emits_warning(self):
        self.run_middleware(404)

        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("WARNING dockbay.requests", lines[0])
        self.assertIn("status=404", lines[0])

    def test_500_response_emits_error(self):
        self.run_middleware(500)

        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("ERROR dockbay.requests", lines[0])
        self.assertIn("status=500", lines[0])

    def test_query_string_is_not_logged(self):
        self.run_middleware(200, "/health/?secret=query-value")

        line = self.log_lines()[0]
        self.assertIn("path=/health/", line)
        self.assertNotIn("secret", line)
        self.assertNotIn("query-value", line)

    def test_exception_is_logged_and_reraised(self):
        def fail(request):
            raise RuntimeError("controlled failure")

        middleware = RequestLoggingMiddleware(fail)

        with self.assertRaisesMessage(RuntimeError, "controlled failure"):
            middleware(self.factory.get("/health/"))

        self.assertEqual(len(self.log_lines()), 1)
        self.assertIn("ERROR dockbay.requests", self.log_lines()[0])
        self.assertIn("status=500", self.log_lines()[0])


class RequestLoggingIntegrationTests(TemporaryRequestLogMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_running_site_writes_info_and_warning_lines(self):
        success = self.client.get("/health/")
        missing = self.client.get("/missing/")

        self.assertEqual(success.status_code, 200)
        self.assertEqual(missing.status_code, 404)
        lines = self.log_lines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(
            lines[0],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} INFO dockbay\.requests ",
        )
        self.assertIn("method=GET path=/health/ status=200", lines[0])
        self.assertIn("WARNING dockbay.requests", lines[1])
        self.assertIn("method=GET path=/missing/ status=404", lines[1])

    def test_running_site_writes_error_line_without_changing_failure(self):
        self.client.raise_request_exception = False

        with patch("registry.views.health_status", side_effect=RuntimeError("controlled failure")):
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 500)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("ERROR dockbay.requests", lines[0])
        self.assertIn("method=GET path=/health/ status=500", lines[0])

    def test_sensitive_request_values_are_not_logged(self):
        self.client.cookies["sessionid"] = "cookie-secret"

        response = self.client.post(
            "/login/?token=query-secret",
            {"username": "private@example.com", "password": "form-secret"},
            HTTP_AUTHORIZATION="Bearer header-secret",
        )

        self.assertEqual(response.status_code, 200)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("method=POST path=/login/ status=200", line)
        for secret in (
            "query-secret",
            "cookie-secret",
            "private@example.com",
            "form-secret",
            "header-secret",
        ):
            self.assertNotIn(secret, line)


class LoggingConfigurationTests(SimpleTestCase):
    def test_application_logger_uses_info_file_handler_without_propagation(self):
        handler = settings.LOGGING["handlers"]["application_file"]
        logger = settings.LOGGING["loggers"]["dockbay.requests"]

        self.assertEqual(handler["class"], "logging.FileHandler")
        self.assertEqual(handler["level"], "INFO")
        self.assertEqual(Path(handler["filename"]), settings.DOCKBAY_LOG_FILE)
        self.assertEqual(logger["handlers"], ["application_file"])
        self.assertEqual(logger["level"], "INFO")
        self.assertFalse(logger["propagate"])

    def test_log_path_uses_environment_override_or_project_default(self):
        expected = Path(
            os.environ.get(
                "DOCKBAY_LOG_FILE",
                os.devnull
                if settings.SKIP_SUPERADMIN_BOOTSTRAP
                else settings.BASE_DIR / "dockbay.log",
            )
        )

        self.assertEqual(settings.DOCKBAY_LOG_FILE, expected)
