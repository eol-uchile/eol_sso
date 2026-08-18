# Python Standard Libraries
from itertools import islice
import logging
import time

# Installed packages (via pip)
from django.db import transaction
from django.db.models import F, Q
from social_django.models import UserSocialAuth
from uchileedxlogin.services.interface import EdxLoginUser

# Internal project dependencies
from .migrate_eol_sso import BaseMigrationCommand
from ...backends import UchileOAuth2Backend
from ...models import UserIndivId
from ...ph_correos_query import get_persona_by_indiv_id_bulk

logger = logging.getLogger(__name__)


class Command(BaseMigrationCommand):
    def handle(self, *args, **options):
        """
        Management command to migrate data from uchileedxlogin.EdxLoginUser
        into UserIndivId and UserSocialAuth.

        This fetches uchile account links and indiv_id information, adds
        data from the persona API (the immutable id_persona key, used as
        UserSocialAuth.uid), and populates UserIndivId/UserSocialAuth
        accordingly. Uses a single bulk API call per batch rather than one
        call per user in order to deal with rate limits.

        Safe to run repeatedly.
        """
        # Check if UserIndivId/UserSocialAuth are in the expected state
        self.check_target_state()
 
        batch_size = options['batch_size']
        sleep_time = options['sleep']
        dry_run = options['dry_run']

        done_with_sso = UserSocialAuth.objects.filter(
            provider=UchileOAuth2Backend.name
        ).values_list('user_id', flat=True)
 
        # Exclude records that don't need to be migrated:
        #   - have_sso=False, and this user's existing UserIndivId.indiv_id already
        #     matches their current run (nothing changed since last migration).
        #   - have_sso=True, and this user already has a matching UserSocialAuth.
        # This makes the command safely re-runnable. Only records that are new or whose
        # relevant fields changed since the last run, get reprocessed.
        queryset = EdxLoginUser.objects.exclude(
            Q(have_sso=False, user__userindivid__indiv_id=F('run')) |
            Q(have_sso=True, user_id__in=done_with_sso)
        ).order_by('id')
        stream = queryset.iterator(chunk_size=batch_size)
 
        logger.info("Starting EdxLoginUser migration")
 
        total_migrated = 0
        total_skipped = 0
 
        while True:
            batch = list(islice(stream, batch_size))
            if not batch:
                break
            # Makes a list of runs/indiv_ids for users that have an sso link
            linked_users = [user.run for user in batch if user.have_sso]
            api_results = {}
            if linked_users:
                try:
                    api_results = get_persona_by_indiv_id_bulk(linked_users)
                except Exception as e:
                    logger.error(f"Error with the PH API call, error: {e}")
                    break
 
            # records without an sso link are handled with update_or_create below, since
            # a stale, already-existing UserIndivId row needs updating.
            no_sso_records = [record for record in batch if not record.have_sso]
 
            indiv_id_entries = []
            social_auth_entries = []
 
            # Iterates over the users with an sso link in the batch
            for record in batch:
                if not record.have_sso:
                    continue
 
                # Retrieve data from the PH API response. If the user is not
                # found in the API response, it means the link is broken, in
                # which case the user is skipped entirely for this run.
                result = api_results.get(record.run, None)
                if not result:
                    logger.warning(f'The user {record} could not be found in the PH API.')
                    total_skipped += 1
                    continue
 
                api_indiv_id = result["indiv_id"]
                if api_indiv_id != record.run:
                    logger.info(
                        f"indiv_id correction for user_id={record.user_id}: stored '{record.run}' -> API '{api_indiv_id}'.")
 
                indiv_id_entries.append(UserIndivId(
                    indiv_id=api_indiv_id,
                    user_id=record.user_id
                ))
                social_auth_entries.append(UserSocialAuth(
                    user_id=record.user_id,
                    provider=UchileOAuth2Backend.name,
                    uid=str(result["id_persona"]),
                ))
 
            try:
                with transaction.atomic():
                    # Records with no sso are processed separately, so we can update the cases
                    # in which the run/indiv_id changed on EdxLoginUser ()
                    for record in no_sso_records:
                        UserIndivId.objects.update_or_create(
                            user_id=record.user_id,
                            defaults={"indiv_id": record.run},
                        )
                    UserIndivId.objects.bulk_create(indiv_id_entries, ignore_conflicts=True)
                    UserSocialAuth.objects.bulk_create(social_auth_entries, ignore_conflicts=True)
                    if dry_run:
                        transaction.set_rollback(True)
                total_migrated += len(no_sso_records) + len(indiv_id_entries)
                logger.info(f"Successful insertion: IDs {batch[0].id} to {batch[-1].id}")
            # If the database save fails, break the loop.
            except Exception as e:
                logger.error(f"DB error when trying to save batch: {e}")
                break
 
            # Given the rate limiter in the PH API, a sleep timer between batches could
            # be necessary.
            if sleep_time > 0:
                time.sleep(sleep_time)
 
        logger.info(f"EdxLoginUser migration complete. Migrated={total_migrated}, Skipped={total_skipped}.")
 