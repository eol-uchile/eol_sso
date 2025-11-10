# Python Standard Libraries
import logging

# Installed packages (via pip)
from django.apps import apps
from django.contrib.auth.models import User
if apps.is_installed('uchileedxlogin'):
    from uchileedxlogin.services.interface import (
        get_doc_id_by_user_id as uchileedxlogin_get_doc_id_by_user_id,
        get_user_id_doc_id_pairs as uchileedxlogin_get_user_id_doc_id_pairs,
        get_user_by_doc_id as uchileedxlogin_get_user_by_doc_id,
        edxloginuser_factory as uchileedxlogin_edxloginuser_factory,
        PhApiException as UchileedxloginPhApiException,
        EmailException as UchileedxloginEmailException
    )
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

def get_indiv_id(user_id):
    """
    Gets the indiv_id associated with user_id.
    Note: Documents of type DNI are not considered in the case of eol_sso_login since eol_sso
    doesn't support that type. Therefore, if a user has an indiv_id of that type, it's going to
    return None.
    """
    if MODEL_USED == 'uchileedxlogin':
        return uchileedxlogin_get_doc_id_by_user_id(user_id)
    elif MODEL_USED == 'eol_sso_login':
        try:
            indiv_id = SSOLoginExtraData.objects.values_list('document').get(type_document__in=['rut', 'passport'], user__id=user_id)
            return indiv_id
        except SSOLoginExtraData.DoesNotExist:
            return None

def get_user_id_with_indiv_id_list(user_id_list):
    """
    Returns a list containing pairs user_id/indiv_id associated with the users in user_id_list.
    Note: Documents of type DNI are not considered in the case of eol_sso_login since eol_sso
    doesn't support that type. Therefore, if a user has an indiv_id of that type, it's going
    to return None.
    """
    if MODEL_USED == 'uchileedxlogin':
        return uchileedxlogin_get_user_id_doc_id_pairs(user_id_list)
    elif MODEL_USED == 'eol_sso_login':
        user_id_with_indiv_id_list = SSOLoginExtraData.objects.filter(type_document__in=['rut', 'passport'], user__id__in=user_id_list).values_list('user__id', 'document')
        return user_id_with_indiv_id_list

def get_user_by_indiv_id(indiv_id):
    """
    Get the user associated with indiv_id, if it doesn't exist, return None.
    """
    if MODEL_USED == 'uchileedxlogin':
        edxloginuser = uchileedxlogin_get_user_by_doc_id(indiv_id)
        if edxloginuser is None:
            return None
        else:
            return edxloginuser.user
    elif MODEL_USED == 'eol_sso_login':
        try:
            user = User.objects.get(ssologinextradata__document=indiv_id, ssologinextradata__type_document__in=['rut', 'passport'])
            return user
        except User.DoesNotExist:
            return None

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
