# Python Standard Libraries
from itertools import islice
import logging
import time

# Installed packages (via pip)
from django.db import connection, transaction
from eol_sso_login.models import SSOLoginCuentaUChile, SSOLoginExtraData

# Internal project dependencies
from ._migrate_eol_sso import BaseMigrationCommand
from ...models import UserSso
from ...ph_query import get_user_data_by_username


logger = logging.getLogger(__name__)


SSOLOGINCUENTAUCHILE_QUERY = """
    INSERT INTO eol_sso_usersso (indiv_id, id_persona, user_id, created, last_updated)
    VALUES (%s, %s, %s, NOW(), NOW())
    ON DUPLICATE KEY UPDATE
        id_persona = VALUES(id_persona),
        user_id= VALUES(user_id),
        last_updated = NOW()
"""

class Command(BaseMigrationCommand):
    def handle(self, *args, **options):
        """
        Management command to migrate data from eol_sso_login SSOLoginCuentaUChile to UserSso and
        afterwards migrate data from SSOLoginExtraData to UserSso.
        This command fetches uchile account link information, adds data from PH API like an
        immutable key, and populates the UserSso table, for data migrated from SSOLoginCuentaUchile.
        """
        
        # Check if UserSso is in expected state
        self.check_user_sso_state()
        
        batch_size = options['batch_size']
        sleep_time = options['sleep']
        dry_run = options['dry_run']

        # Start migrating from Login Cuenta Uchile Table, if there is an error, stop the
        # migration proccess
        if not self.migrate_login_cuenta_uchile(batch_size, sleep_time, dry_run):
            logger.error(f'Migration failed when proccesing LoginCuentaUchile Table')
            return

        # Start migrating from Extra Data table
        if not self.migrate_extra_data(batch_size, dry_run):
            logger.error(f'Migration failed when proccesing ExtraData Table')
            return

    def migrate_login_cuenta_uchile(self, batch_size, sleep_time, dry_run):
        """
        Migrates data from eol_sso_login LoginCuentaUchile Table to EolSso
        """
        # Start migrating from Login Cuenta Uchile Table
        latest = UserSso.objects.filter(id_persona__isnull=False).order_by('-created').first()
        # starter_id is the highest id in the origin table of the already proccesed users, and
        # its used as to not go though all the users again when running the command a second time
        starter_id = latest.user.ssologincuentauchile.id if latest else 0
   
        queryset = SSOLoginCuentaUChile.objects.filter(id__gt=starter_id).select_related('user').order_by('id')
        stream = queryset.iterator(chunk_size=batch_size)
        
        while True:
            batch = list(islice(stream, batch_size))
            if not batch:
                break
            
            linked_users = [user.username for user in batch if user.is_active]
            api_results = {}
            if linked_users:
                try:
                    api_results = get_user_data_by_username(linked_users)
                except Exception as e:
                    logger.error(f"Error with the PH API call, error: {e}")
                    return False

            new_records = []
            for record in batch:
                result = api_results.get(record.username, None)
                if result:
                    new_records.append((result['indiv_id'], result['id_persona'], record.user.id))
                else:
                    logger.warning(f'The user {record} could not be found in the PH API.')
            try:
                with transaction.atomic():            
                    with connection.cursor() as cursor:
                        cursor.executemany(SSOLOGINCUENTAUCHILE_QUERY, new_records)
                    if dry_run:
                        transaction.set_rollback(True)
                logger.info(f"Success: IDs {batch[0].id} to {batch[-1].id}")
            # If the database save fails, break the loop.
            except Exception as e:
                logger.error((f"DB error when trying to insert into the Database: {e}, for objects: {new_records}"))
                return False
            if sleep_time > 0:
                time.sleep(sleep_time)
        # End migration from Login Cuenta Uchile Table
        logger.info("LoginCuentaUchile migration complete")
        return True
    
    def migrate_extra_data(self, batch_size, dry_run):
        """
        Migrates data from eol_sso_login ExtraData Table to EolSso
        """
        latest_user = UserSso.objects.filter(id_persona__isnull=True).order_by('-created').first()
        # starter_id is the highest id in the origin table of the already proccesed users, and its
        # used as to not go though all the users again when running the command a second time
        starter_id = latest_user.user.ssologinextradata.id if latest_user else 0

        queryset = SSOLoginExtraData.objects.filter(id__gt=starter_id).select_related('user').order_by('id')
        stream = queryset.iterator(chunk_size=batch_size)
        
        while True:
            batch = list(islice(stream, batch_size))

            if not batch:
                logger.info(f"There isn't any data to migrate")
                break

            new_records = []
            for entry in batch:
                # DNI type indiv_ids are ignored
                if entry.type_document == 'dni':
                    continue
                # Format passport type documents to make sure they start with P following
                # PH format
                elif entry.type_document == 'passport':
                    if entry.document[0] != 'P':
                        entry.document = f'P{entry.document}'
                new_records.append(UserSso(
                    indiv_id=entry.document,
                    user=entry.user
                ))
            try:
                with transaction.atomic():
                    # Registers with unique key collisions are ignored due to overlap between
                    # entries from ExtraData and LoginCuentaUchile table
                    UserSso.objects.bulk_create(new_records, ignore_conflicts=True)
                    if dry_run:
                        transaction.set_rollback()
            except Exception as e:
                return False
        logger.info("ExtraData migration complete")
        return True
