import importlib
import os
from unittest.mock import patch
from django.test import SimpleTestCase
from dockbay import settings


class DatabaseChoiceTest(SimpleTestCase):
    def test_uses_sqlite_when_uks_test_db_is_on(self):
        with patch.dict(os.environ, {"UKS_TEST_DB": "ON"}):
            importlib.reload(settings)
            self.assertEqual(
                settings.DATABASES["default"]["ENGINE"],
                "django.db.backends.sqlite3",
            )

    def test_uses_postgres_when_uks_test_db_is_unset(self):
        env_without_flag = {k: v for k, v in os.environ.items() if k != "UKS_TEST_DB"}
        with patch.dict(os.environ, env_without_flag, clear=True):
            importlib.reload(settings)
            self.assertEqual(
                settings.DATABASES["default"]["ENGINE"],
                "django.db.backends.postgresql",
            )