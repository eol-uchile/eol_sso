# Python Standard Libraries
from http import HTTPStatus
import logging
import requests

# Installed packages (via pip)
from django.conf import settings
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

    def get_user_data(self, query_values, query_type):
        """
        Get the users data from PH API, query types can be either indiv_id or usuario.
        It makes a single query for all values in query_values, if some values are not found
        in PH, they won't be on the return value. If not a single value is found return an
        empty dictionary.
        """
        if query_type not in ["indiv_id", "usuario"]:
            raise ValueError("query_type must be either 'indiv_id' or 'usuario'")
        headers = {
            'AppKey': settings.SSOLOGIN_UCHILE_KEY,
            'Origin': settings.LMS_ROOT_URL
        }
        quoted_values = [f'"{v}"' for v in query_values]
        query_string = ",".join(quoted_values)
        params = {
            query_type: query_string
        }
        result = requests.get(settings.BASE_EOL_SSO_API_URL, headers=headers, params=params)
        if result.status_code == HTTPStatus.NO_CONTENT:
            return {}
        if result.status_code != HTTPStatus.OK:
            logger.error(
                "PH API returned unexpected status code: {}, data: {}".format(
                    result.status_code, query_values))
            raise Exception(
                "PH API returned unexpected status code: {}, data: {}".format(
                    result.status_code, query_values))
        
        data = result.json()
        if data["data"]["getRowsPersona"] is None:
            logger.error(
                "Missing 'getRowsPersona' in API response, status_code: {}, body: {}, query_value: {}".format(
                    result.status_code,
                    result.text,
                    query_values))
            raise Exception(
                "Missing 'getRowsPersona' in API response, status_code: {}, query_value: {}".format(
                    result.status_code, query_values))
        if data['data']['getRowsPersona']['status_code'] != HTTPStatus.OK:
            logger.error(
                "PH API returned error status {}, expected 200, body: {}, username: {}".format(
                    data['data']['getRowsPersona']['status_code'],
                    result.text,
                    query_values))
            raise Exception(
                "PH API returned error status {}, expected 200, query_value: {}".format(
                    result.status_code, query_values))
        return data
    
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
