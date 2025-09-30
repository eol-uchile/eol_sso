# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.apps import apps
if apps.is_installed('uchileedxlogin'):
    from uchileedxlogin.services.interface import (
        get_doc_id_by_user_id as uchileedxlogin_get_doc_id_by_user_id,
        get_user_id_doc_id_pairs as uchileedxlogin_get_user_id_doc_id_pairs,
        get_user_by_doc_id as uchileedxlogin_get_user_by_doc_id,
        edxloginuser_factory as uchileedxlogin_edxloginuser_factory,
        PhApiException as UchileedxloginPhApiException,
        EmailException as UchileedxloginEmailException
    )
    from uchileedxlogin.services.utils import get_document_type as uchileedxlogin_get_document_type
    MODEL_USED = 'uchileedxlogin'
elif apps.is_installed('eol_sso_login'):
    from eol_sso_login.models import SSOLoginExtraData
    MODEL_USED = 'eol_sso_login'
else:
    raise ImportError(f"You must have either uchileedxlogin or eol_sso_login installed")


logger = logging.getLogger(__name__)

# Interface exceptions.
class PhApiException(Exception):
    """
    Raised to indicate that the data related to the value provided to ph failed to get retrieved.
    """

class EmailException(Exception):
    """
    Raised to indicate that none of the mails associated with the doc_id are valid to create a
    edx user.
    """

def get_doc_id_by_user_id(user_id):
    """
    Return the document id associated with the user. If there is not a user with that id, returns None.
    """
    if MODEL_USED == 'uchileedxlogin':
        return uchileedxlogin_get_doc_id_by_user_id(user_id)
    elif MODEL_USED == 'eol_sso_login':
        try:
            doc_id = SSOLoginExtraData.objects.values_list('document', flat=True).get(user__id=user_id)
            return doc_id
        except SSOLoginExtraData.DoesNotExist:
            return None

def get_user_id_doc_id_pairs(user_ids):
    """
    Returns a list containing the pairs user_id/doc_id associated with the users in user_ids.
    """
    if MODEL_USED == 'uchileedxlogin':
        return uchileedxlogin_get_user_id_doc_id_pairs(user_ids)
    elif MODEL_USED == 'eol_sso_login':
        users_doc_id_pairs = SSOLoginExtraData.objects.filter(user__id__in=user_ids).values_list('user__id', 'document')
        return users_doc_id_pairs

def get_user_by_doc_id(doc_id, doc_type):
    """
    Get the user associated with doc_id, if it doesn't exists, return None.
    Doesn't work with eol_sso_login.
    """
    if MODEL_USED == 'uchileedxlogin':
        return uchileedxlogin_get_user_by_doc_id(doc_id)
    elif MODEL_USED == 'eol_sso_login':
        raise NotImplementedError("Not supported")

def sso_user_factory(value, value_type):
    """
    Create an sso user using value. Verifies if the value is valid.
    Tries to match the value with an already existing edx user, if it
    can't, creates a new edx user.
    The only value_type supported is doc_id.
    Doesn't work with eol_sso_login.
    """
    if MODEL_USED == 'uchileedxlogin':
        try:
            return uchileedxlogin_edxloginuser_factory(value, value_type)
        except UchileedxloginPhApiException:
            raise PhApiException()
        except UchileedxloginEmailException:
            raise EmailException()
    else:
        raise NotImplementedError("Not supported")

def get_document_type(doc_id):
    """
    Get the document type of a document id.
    """
    if MODEL_USED == 'uchileedxlogin':
        return uchileedxlogin_get_document_type(doc_id)
    elif MODEL_USED == 'eol_sso_login':
        try:
            document_type = SSOLoginExtraData.objects.get(document=doc_id).type_document
            return document_type
        except SSOLoginExtraData.DoesNotExist:
            return None
