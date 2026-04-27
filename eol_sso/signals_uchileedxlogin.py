# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from uchileedxlogin.services.interface import EdxLoginUser

# Internal project dependencies
from .models import UserSso
from .ph_query import get_user_data_by_indiv_id

logger = logging.getLogger(__name__)

@receiver(post_save, sender=EdxLoginUser)
def sync_sso_data(sender, instance, **kwargs):
    """
    Synchronizes UserSso records whenever an EdxLoginUser is saved
    """
    # Get the base tuple
    sso_record = UserSso.objects.filter(user_id=instance.user_id).first()
    needs_save = False

    if not sso_record:
        sso_record = UserSso(user_id=instance.user_id)
        needs_save = True

    # Sync indiv_id if it changed
    if sso_record.indiv_id != instance.run:
        sso_record.indiv_id = instance.run
        needs_save = True

    # Handle id_persona, only try to fetch from ph if have_sso is True and
    # we are currently missing id_persona
    if instance.have_sso:
        if sso_record.id_persona is None:
            try:
                api_response_map = get_user_data_by_indiv_id([instance.run])
            
                # Extract the specific id_persona for this run
                user_info = api_response_map.get(instance.run)

                if user_info and user_info.get('id_persona'):
                    sso_record.id_persona = user_info['id_persona']
                    needs_save = True
            except Exception as e:
                # If there is an error with the query, we skip this signal
                logger.error(f"Failed to fetch indiv_id for {instance.run}: {e}")
                return
    else:
        # Link is inactive, so id_persona must not exist
        if sso_record.id_persona is not None:
            sso_record.id_persona = None
            needs_save = True

    # Save iif something actually changed
    if needs_save:
        sso_record.save()

@receiver(post_delete, sender=EdxLoginUser)
def cleanup_sso_data(sender, instance, **kwargs):
    """
    Deletes UserSso row whenever the matching EdxLoginUser row is deleted
    """
    UserSso.objects.filter(user_id=instance.user_id).delete()
    logger.info(f"Cleaned up UserSso for user {instance.user_id} due to EdxLoginUser deletion.")
