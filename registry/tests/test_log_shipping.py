import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from registry.logs import parse_log_line, ship_log_batch


INFO_LINE = (
    "2026-11-13T10:15:22+0000 INFO dockbay.requests "
    "request completed method=GET path=/health/ status=200\n"
)
WARNING_LINE = (
    "2026-11-13T10:16:22+0000 WARNING dockbay.requests "
    "request completed method=GET path=/missing/ status=404\n"
)
ERROR_LINE = (
    "2026-11-13T10:17:22+0000 ERROR dockbay.requests "
    "request completed method=GET path=/health/ status=500\n"
)


class FakeIndices:
    def __init__(self):
        self.created = []

    def exists(self, **kwargs):
        return bool(self.created)

    def create(self, **kwargs):
        self.created.append(kwargs)


class FakeClient:
    def __init__(self):
        self.indices = FakeIndices()


class LogShippingTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.log_path = Path(self.directory.name) / "dockbay.log"
        self.checkpoint_path = Path(self.directory.name) / "dockbay.log.checkpoint"
        self.client = FakeClient()

    def tearDown(self):
        self.directory.cleanup()

    def test_inherited_log_line_is_parsed(self):
        self.assertEqual(
            parse_log_line(INFO_LINE.rstrip("\n")),
            {
                "timestamp": "2026-11-13T10:15:22+00:00",
                "level": "INFO",
                "logger": "dockbay.requests",
                "message": "request completed method=GET path=/health/ status=200",
            },
        )

    def test_checkpoint_sends_only_complete_new_lines(self):
        self.log_path.write_text(INFO_LINE + WARNING_LINE, encoding="utf-8")
        batches = []

        self.assertEqual(
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                lambda _client, actions: batches.append(actions),
            ),
            2,
        )
        first_checkpoint = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        self.assertEqual(first_checkpoint["offset"], self.log_path.stat().st_size)
        self.assertEqual(
            self.client.indices.created[0]["mappings"]["properties"],
            {
                "timestamp": {"type": "date"},
                "level": {"type": "keyword"},
                "logger": {"type": "keyword"},
                "message": {"type": "text"},
            },
        )

        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(ERROR_LINE)
            log_file.write("2026-11-13T10:18:22+0000 INFO dockbay.requests partial")
        self.assertEqual(
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                lambda _client, actions: batches.append(actions),
            ),
            1,
        )
        self.assertEqual([len(batch) for batch in batches], [2, 1])
        self.assertEqual(batches[1][0]["_source"]["level"], "ERROR")
        second_checkpoint = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        self.assertEqual(
            second_checkpoint["offset"],
            len((INFO_LINE + WARNING_LINE + ERROR_LINE).encode()),
        )

    def test_failed_bulk_does_not_advance_checkpoint_and_retry_ids_are_stable(self):
        self.log_path.write_text(INFO_LINE, encoding="utf-8")
        ship_log_batch(
            self.log_path,
            self.checkpoint_path,
            self.client,
            lambda _client, _actions: None,
        )
        checkpoint = self.checkpoint_path.read_text(encoding="utf-8")
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(ERROR_LINE)

        attempts = []

        def fail(_client, actions):
            attempts.append(actions)
            raise RuntimeError("bulk failed")

        with self.assertRaisesMessage(RuntimeError, "bulk failed"):
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                fail,
            )
        self.assertEqual(self.checkpoint_path.read_text(encoding="utf-8"), checkpoint)

        ship_log_batch(
            self.log_path,
            self.checkpoint_path,
            self.client,
            lambda _client, actions: attempts.append(actions),
        )
        self.assertEqual(attempts[0][0]["_id"], attempts[1][0]["_id"])

    def test_missing_empty_truncated_and_rotated_files_are_safe(self):
        calls = []
        bulk_function = lambda _client, actions: calls.append(actions)
        self.assertEqual(
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                bulk_function,
            ),
            0,
        )
        self.log_path.write_text("", encoding="utf-8")
        self.assertEqual(
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                bulk_function,
            ),
            0,
        )

        self.log_path.write_text(INFO_LINE + WARNING_LINE, encoding="utf-8")
        ship_log_batch(self.log_path, self.checkpoint_path, self.client, bulk_function)
        self.log_path.write_text(ERROR_LINE, encoding="utf-8")
        self.assertEqual(
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                bulk_function,
            ),
            1,
        )
        rotated = self.log_path.with_suffix(".old")
        self.log_path.replace(rotated)
        self.log_path.write_text(WARNING_LINE, encoding="utf-8")
        self.assertEqual(
            ship_log_batch(
                self.log_path,
                self.checkpoint_path,
                self.client,
                bulk_function,
            ),
            1,
        )
