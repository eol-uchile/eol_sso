# Python Standard Libraries
from itertools import islice
import logging
import time

# Installed packages (via pip)
from django.db import transaction
from uchileedxlogin.services.interface import EdxLoginUser

# Internal project dependencies
from ._migrate_eol_sso import BaseMigrationCommand
from ...models import UserSso
from ...ph_query import get_user_data_by_indiv_id

logger = logging.getLogger(__name__)


class Command(BaseMigrationCommand):
    def handle(self, *args, **options):
        """
        Management command to migrate data from uchileedxlogin EdxLoginUser to UserSso.
        This command fetches uchile account links and indiv_id information, adds data from PH API
        like an immutable key, and populates the UserSso table.
        """
        
        # Check if UserSso is in expected state
        self.check_user_sso_state()
        
        batch_size = options['batch_size']
        sleep_time = options['sleep']
        dry_run = options['dry_run']

        queryset = EdxLoginUser.objects.filter(
                                user__usersso__isnull=True
                            ).order_by('id')
        stream = queryset.iterator(chunk_size=batch_size)
        
        logger.info(f"Starting EdxLoginUser migration")

        while True:
            batch = list(islice(stream, batch_size))
            
            if not batch:
                break
            
            # Makes a list of runs/indiv_ids for users that have an sso link
            linked_users = [user.run for user in batch if user.have_sso]
            api_results = {}
            if linked_users:
                try:
                    api_results = get_user_data_by_indiv_id(linked_users)
                except Exception as e:
                    logger.error(f"Error with the PH API call, error: {e}")
                    break

            new_entries = []
            # Iterates over the users in the batch
            for record in batch:
                # If the user doesn't have a linked uchile account, pass the data as is
                if not record.have_sso:
                    new_entries.append(UserSso(
                                indiv_id=record.run,
                                user_id=record.user_id
                            ))
                # If the user does have a linked uchile account, retrieve its data from the
                # PH API response and add it to new_entries. If the user is not found in the
                # API response, it means that the link is broken, in which case the user data
                # is not added to UserSso
                else:
                    result = api_results.get(record.run, None)
                    if result:
                        id_persona = result["id_persona"]
                        if id_persona is not None:
                            new_entries.append(UserSso(
                                indiv_id=record.run,
                                id_persona=id_persona,
                                user=record.user
                            ))
                    else:
                        logger.warning(f'The user {record} could not be found in the PH API.')
            try:
                with transaction.atomic():
                    UserSso.objects.bulk_create(new_entries, ignore_conflicts=True)
                    if dry_run:
                        transaction.set_rollback(True)
                logger.info(f"Successful insertion: IDs {batch[0].id} to {batch[-1].id}")
            # If the database save fails, break the loop.
            except Exception as e:
                logger.error((f"DB error when trying to bulk_create: {e}, for objects: {new_entries}"))
                break

            # Given the limit of 5000 request per minute in the PH API, a sleep timer between batches
            # could be necessary.
            if sleep_time > 0:
                time.sleep(sleep_time)
        logger.info("Edxloginuser migration complete")
