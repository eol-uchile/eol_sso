# Python Standard Libraries
from http import HTTPStatus
import logging
import requests

# Installed packages (via pip)
from django.conf import settings

logger = logging.getLogger(__name__)

def _get_user_data(query_values, query_type):
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

def get_user_data_by_indiv_id(query_values):
        """
        get_user_data wrapper for the case when needing user information about users querying
        by indiv_id
        """
        data = _get_user_data(query_values, 'indiv_id')
        # Iterate over the users
        user_data = {}
        for user in data["data"]["getRowsPersona"]['persona']:
            user_data[user['indiv_id']] = {
                'indiv_id': user['indiv_id'],
                'id_persona': user['id_persona']
            }
        return user_data

def get_user_data_by_username(query_values):
        """
        get_user_data wrapper for the case when needing user information about users querying
        by username/usuario
        """
        data = _get_user_data(query_values, 'usuario')
        # Iterate over the users
        user_data = {}
        for user in data["data"]["getRowsPersona"]['persona']:
            user_data[user['pasaporte'][0]['usuario']] = {
                        'indiv_id': user['indiv_id'],
                        'id_persona': user['id_persona']
                    }
        return user_data
