# Python Standard Libraries
from itertools import islice
import logging
import time

# Installed packages (via pip)
from django.db import transaction
from django.db.models import Q
from social_django.models import UserSocialAuth
from eol_sso_login.models import SSOLoginCuentaUChile, SSOLoginExtraData

# Internal project dependencies
from .migrate_eol_sso import BaseMigrationCommand
from ...backends import UchileOAuth2Backend
from ...models import UserIndivId
from ...ph_query import get_persona_by_username_bulk

logger = logging.getLogger(__name__)


class Command(BaseMigrationCommand):
    def handle(self, *args, **options):
        """
        Management command to migrate data from eol_sso_login's
        SSOLoginCuentaUChile and SSOLoginExtraData into UserIndivId and
        UserSocialAuth.

        Runs in two stages, in this order (technically the order doesn't matter):
          1. SSOLoginCuentaUChile -> UserIndivId and UserSocialAuth, via the
             persona API (keyed by username).
          2. SSOLoginExtraData -> UserIndivId only, no API call.
        """
        # Check if UserIndivId/UserSocialAuth are in the expected state
        self.check_target_state()

        batch_size = options['batch_size']
        sleep_time = options['sleep']
        dry_run = options['dry_run']

        # Start migrating from SSOLoginCuentaUChile Table, if there is an error, stop the
        # migration proccess
        if not self.migrate_login_cuenta_uchile(batch_size, sleep_time, dry_run):
            logger.error('Migration failed when proccesing SSOLoginCuentaUChile Table')
            return

        # Start migrating from SSOLoginExtraData table
        if not self.migrate_extra_data(batch_size, dry_run):
            logger.error('Migration failed when proccesing SSOLoginExtraData Table')
            return

    def migrate_login_cuenta_uchile(self, batch_size, sleep_time, dry_run):
        """
        Migrates data from eol_sso_login SSOLoginCuentaUChile into
        UserIndivId and UserSocialAuth.

        Only is_active=True records are considered, unlike
        EdxLoginUser, there's no data worth preserving for inactive
        records here, so they're excluded from the queryset entirely
        rather than processed and skipped.

        UserIndivId is written via update_or_create rather than bulk_create.
        This matters across separate runs of this command over time, since
        it lets the command update stale indiv_ids, for example in the case
        a user that had an entry on UserIndivId but no sso link, later gets
        an sso link, this will force the indiv_id to be updated to the one found
        on the API response.
        """
        done_with_sso = UserSocialAuth.objects.filter(
            provider=UchileOAuth2Backend.name
        ).values_list('user_id', flat=True)

        # Exclude records that don't need to be migrated:
        #   - users with no confirmed sso link.
        #   - users with an sso link on SSOLoginCuentaUChile and who alreade have a matching UserSocialAuth.
        queryset = SSOLoginCuentaUChile.objects.exclude(
            Q(is_active=False) |
            Q(is_active=True, user_id__in=done_with_sso)
        ).order_by('id')
        stream = queryset.iterator(chunk_size=batch_size)

        total_migrated = 0
        total_skipped = 0

        while True:
            batch = list(islice(stream, batch_size))
            if not batch:
                break

            linked_users = [user.username for user in batch]
            api_results = {}
            if linked_users:
                try:
                    api_results = get_persona_by_username_bulk(linked_users)
                except Exception as e:
                    logger.error(f"Error with the PH API call, error: {e}")
                    return False

            confirmed = []
            social_auth_entries = []
            for record in batch:
                result = api_results.get(record.username, None)
                if not result:
                    logger.warning(f'The user {record} could not be found in the PH API.')
                    total_skipped += 1
                    continue

                confirmed.append((record.user_id, result["indiv_id"]))
                social_auth_entries.append(UserSocialAuth(
                    user_id=record.user_id,
                    provider=UchileOAuth2Backend.name,
                    uid=str(result["id_persona"]),
                ))

            try:
                with transaction.atomic():
                    for user_id, indiv_id in confirmed:
                        UserIndivId.objects.update_or_create(
                            user_id=user_id,
                            defaults={"indiv_id": indiv_id},
                        )
                    UserSocialAuth.objects.bulk_create(social_auth_entries, ignore_conflicts=True)
                    if dry_run:
                        transaction.set_rollback(True)
                total_migrated += len(confirmed)
                logger.info(f"Success: IDs {batch[0].id} to {batch[-1].id}")
            except Exception as e:
                logger.error(f"DB error when trying to save batch: {e}")
                return False

            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.info(f"LoginCuentaUchile migration complete. Migrated={total_migrated}, Skipped={total_skipped}")

        return True

    def migrate_extra_data(self, batch_size, dry_run):
        """
        Migrates data from eol_sso_login SSOLoginExtraData into UserIndivId.

        Excludes users with an sso link, so that the indiv_id from SSOLoginExtraData doesn't
        overwrite the one from the API.
        For selected users, updates indiv_id from SSOLoginExtraData even if there is already
        an entry on UserIndivId.
        DNI type documents are ignored, and passport ones are formatted to PH follow format.
        """
        done_with_sso = UserSocialAuth.objects.filter(
            provider=UchileOAuth2Backend.name
        ).values_list('user_id', flat=True)

        queryset = SSOLoginExtraData.objects.exclude(
            user_id__in=done_with_sso
        ).order_by('id')
        stream = queryset.iterator(chunk_size=batch_size)

        total_migrated = 0
        total_dni_skipped = 0

        while True:
            batch = list(islice(stream, batch_size))

            if not batch:
                break

            new_entries = []
            for entry in batch:
                if entry.type_document == 'dni':
                    total_dni_skipped += 1
                    continue
                document = entry.document
                # Format passports to the same format in PH API.
                if entry.type_document == 'passport' and not document.startswith('P'):
                    document = f'P{document}'
                new_entries.append((entry.user_id, document))

            try:
                with transaction.atomic():
                    # Update the indiv_id if there was a change on it. Users with an
                    # already created sso link are filtrated earlier in the function so
                    # that their indiv_id is not changed.
                    for user_id, indiv_id in new_entries:
                        _, created = UserIndivId.objects.update_or_create(
                            user_id=user_id,
                            defaults={"indiv_id": indiv_id},
                        )
                        if created:
                            total_migrated += 1
                    if dry_run:
                        transaction.set_rollback(True)
                logger.info(f"Success: IDs {batch[0].id} to {batch[-1].id}")
            except Exception as e:
                logger.error(f"DB error when trying to bulk_create: {e}")
                return False

        logger.info(f"ExtraData migration complete. Migrated={total_migrated}, skipped(DNI):{total_dni_skipped}.")
        return True
