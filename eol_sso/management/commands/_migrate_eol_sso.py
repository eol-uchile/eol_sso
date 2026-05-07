# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# Internal project dependencies
from ...models import UserSso


logger = logging.getLogger(__name__)


class BaseMigrationCommand(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--batch_size', type=int, default=100)
        parser.add_argument('--sleep', type=float, default=0.1)
        parser.add_argument('--dry_run', action='store_true')
    
    def check_user_sso_state(self):
        """
        Checks if UserSso table exists and has the expected columns
        """
        table_name = UserSso._meta.db_table
        expected_fields = [f.column for f in UserSso._meta.fields]
        
        # Check if UserSso exists in the database
        if table_name not in connection.introspection.table_names():
            raise CommandError(f"Database error: UserSso does not exist!")

        # Check for missing columns
        with connection.cursor() as cursor:
            columns = [col.name for col in connection.introspection.get_table_description(cursor, table_name)]
            
        missing = [f for f in expected_fields if f not in columns]
        if missing:
            raise CommandError(f"Schema mismatch: Table '{table_name}' is missing columns: {missing}")
        
        logger.info(f"UserSso is in the same state as expected.")
