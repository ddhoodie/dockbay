from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from registry.logs import (
    LogQueryError,
    LogSearchUnavailable,
    build_elasticsearch_query,
    parse_log_query,
    search_logs,
)
from registry.models import User


EXAMPLE_QUERY = '(warning OR error) AND "error occured"'
EXAMPLE_DSL = {
    "bool": {
        "filter": [
            {
                "bool": {
                    "should": [
                        {"bool": {"filter": [{"term": {"level": "WARNING"}}]}},
                        {"bool": {"filter": [{"term": {"level": "ERROR"}}]}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        ],
        "must": [{"match_phrase": {"message": "error occured"}}],
    }
}


class LogQueryTests(SimpleTestCase):
    def test_example_query_uses_level_filters_and_a_scored_phrase(self):
        self.assertEqual(build_elasticsearch_query(EXAMPLE_QUERY), EXAMPLE_DSL)

    def test_not_then_and_then_or_precedence_and_parentheses(self):
        self.assertEqual(
            parse_log_query("info OR warning AND NOT error"),
            (
                "OR",
                ("level", "INFO"),
                ("AND", ("level", "WARNING"), ("NOT", ("level", "ERROR"))),
            ),
        )
        self.assertEqual(
            parse_log_query("(info OR warning) AND error"),
            (
                "AND",
                ("OR", ("level", "INFO"), ("level", "WARNING")),
                ("level", "ERROR"),
            ),
        )

    def test_not_uses_must_not_without_scoring(self):
        self.assertEqual(
            build_elasticsearch_query("NOT word:error"),
            {
                "bool": {
                    "filter": [
                        {"bool": {"must_not": [{"match": {"message": "error"}}]}}
                    ]
                }
            },
        )

    def test_time_bound_uses_a_strict_range_filter(self):
        self.assertEqual(
            build_elasticsearch_query("after:2026-11-13T10:00:00+01:00"),
            {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "timestamp": {"gt": "2026-11-13T10:00:00+01:00"}
                            }
                        }
                    ]
                }
            },
        )

    def test_invalid_syntax_and_timestamps_are_rejected(self):
        invalid_queries = (
            "warning AND",
            "warning error",
            "(warning OR error",
            '"unclosed',
            'word"unclosed',
            "during:2026-11-13T10:00:00+01:00",
            "before:2026-11-13T10:00:00",
            "after:not-a-time",
        )

        for query in invalid_queries:
            with self.subTest(query=query), self.assertRaises(LogQueryError):
                build_elasticsearch_query(query)


class ElasticsearchSearchTests(SimpleTestCase):
    @patch("registry.logs.get_elasticsearch_client")
    def test_search_requests_relevance_order_and_preserves_returned_order(self, get_client):
        client = Mock()
        get_client.return_value = client
        client.search.return_value = {
            "hits": {
                "hits": [
                    {"_source": {"message": "first"}, "_score": 4.0},
                    {"_source": {"message": "second"}, "_score": 2.0},
                ]
            }
        }
        query = {"match": {"message": "error"}}

        results = search_logs(query)

        self.assertEqual(
            [result["message"] for result in results],
            ["first", "second"],
        )
        client.search.assert_called_once_with(
            index="dockbay-logs",
            query=query,
            size=100,
            sort=[
                {"_score": {"order": "desc"}},
                {"timestamp": {"order": "desc", "unmapped_type": "date"}},
            ],
        )


class LogSearchPageTests(TestCase):
    def setUp(self):
        self.administrator = User.objects.create_user(
            username="ana",
            password="ana-admin-pass-1",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username="milan",
            password="milan-pass-1",
        )

    @patch("registry.views.search_logs")
    def test_administrator_submits_example_and_keeps_relevance_order(self, search_logs):
        search_logs.return_value = [
            {
                "timestamp": "2026-11-13T10:15:22+00:00",
                "level": "ERROR",
                "logger": "dockbay.requests",
                "message": "highest relevance <first>",
                "score": 3.5,
            },
            {
                "timestamp": "2026-11-13T10:14:22+00:00",
                "level": "WARNING",
                "logger": "dockbay.requests",
                "message": "lower relevance second",
                "score": 1.25,
            },
        ]
        self.client.login(username="ana", password="ana-admin-pass-1")

        response = self.client.get("/administrators/logs/", {"query": EXAMPLE_QUERY})

        self.assertEqual(response.status_code, 200)
        search_logs.assert_called_once_with(EXAMPLE_DSL)
        content = response.content.decode()
        self.assertLess(
            content.index("highest relevance"),
            content.index("lower relevance"),
        )
        self.assertContains(response, "highest relevance &lt;first&gt;", html=True)

    @patch("registry.views.search_logs")
    def test_time_bound_reaches_elasticsearch_as_a_range_filter(self, search_logs):
        search_logs.return_value = []
        self.client.login(username="ana", password="ana-admin-pass-1")

        self.client.get(
            "/administrators/logs/",
            {"query": "before:2026-11-13T12:00:00+01:00"},
        )

        search_logs.assert_called_once_with(
            {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "timestamp": {"lt": "2026-11-13T12:00:00+01:00"}
                            }
                        }
                    ]
                }
            }
        )

    def test_ordinary_user_is_forbidden_and_anonymous_user_is_redirected(self):
        self.client.login(username="milan", password="milan-pass-1")
        self.assertEqual(self.client.get("/administrators/logs/").status_code, 403)

        self.client.logout()
        response = self.client.get("/administrators/logs/")
        self.assertRedirects(response, "/login/?next=/administrators/logs/")

    @patch("registry.views.search_logs")
    def test_invalid_input_shows_an_error_without_searching(self, search_logs):
        self.client.login(username="ana", password="ana-admin-pass-1")

        response = self.client.get(
            "/administrators/logs/",
            {"query": "warning AND"},
        )

        self.assertContains(response, "A search criterion is missing.")
        search_logs.assert_not_called()

    @patch("registry.views.search_logs", side_effect=LogSearchUnavailable)
    def test_elasticsearch_failure_is_safe(self, search_logs):
        self.client.login(username="ana", password="ana-admin-pass-1")

        response = self.client.get(
            "/administrators/logs/",
            {"query": "error"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log search is temporarily unavailable.")
        self.assertNotContains(response, "http://localhost:9200")
        search_logs.assert_called_once()

    @patch("registry.views.search_logs")
    def test_empty_initial_page_does_not_search(self, search_logs):
        self.client.login(username="ana", password="ana-admin-pass-1")

        response = self.client.get("/administrators/logs/")

        self.assertEqual(response.status_code, 200)
        search_logs.assert_not_called()
