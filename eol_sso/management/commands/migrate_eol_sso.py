# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from social_django.models import UserSocialAuth

# Internal project dependencies
from ...models import UserIndivId

logger = logging.getLogger(__name__)

# Guarantees any migration command using get_sleep_time() can never
# exceed the limit, even if a caller passes --sleep 0 or a value that's too small.
MIN_SLEEP_SECONDS = 0.03


class BaseMigrationCommand(BaseCommand):
    """
    Shared argument parsing and schema sanity-checks for eol_sso migration
    commands.
    """

    def add_arguments(self, parser):
        parser.add_argument('--batch_size', type=int, default=100)
        parser.add_argument('--sleep', type=float, default=0.1)
        parser.add_argument('--dry_run', action='store_true')

    def get_sleep_time(self, options):
        """
        Returns the sleep time to use between batches, clamped to never go
        below MIN_SLEEP_SECONDS. Commands making at most one bulk PH API
        call per batch should sleep this long afterward to stay within the
        rate limit regardless of what --sleep was passed as.
        """
        return max(options['sleep'], MIN_SLEEP_SECONDS)

    def check_target_state(self):
        """
        Checks that UserIndivId and social_django's UserSocialAuth both
        exist and have the expected columns, before a migration run starts
        writing to them.
        """
        for model in (UserIndivId, UserSocialAuth):
            table_name = model._meta.db_table
            expected_fields = [f.column for f in model._meta.fields]

            if table_name not in connection.introspection.table_names():
                raise CommandError(f"Database error: {table_name} does not exist!")

            with connection.cursor() as cursor:
                columns = [
                    col.name for col in
                    connection.introspection.get_table_description(cursor, table_name)
                ]
                missing = [f for f in expected_fields if f not in columns]
                if missing:
                    raise CommandError(
                        f"Schema mismatch: Table '{table_name}' is missing columns: {missing}"
                    )

        logger.info("UserIndivId and UserSocialAuth are in the expected state.")
