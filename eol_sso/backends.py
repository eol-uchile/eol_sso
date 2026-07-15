# Installed packages (via pip)
from django.conf import settings
from social_core.backends.oauth import BaseOAuth2

# Internal project dependencies
from eol_sso.models import UserIndivId


class UchileOAuth2Backend(BaseOAuth2):
    """
    Custom OAuth2 backend for Uchile SSO.
    """

    name = "uchile-oauth2"

    AUTHORIZATION_URL = settings.UCHILE_OAUTH2_AUTHORIZATION_URL
    ACCESS_TOKEN_URL = settings.UCHILE_OAUTH2_ACCESS_TOKEN_URL
    USER_DATA_URL = settings.UCHILE_OAUTH2_USER_DATA_URL

    REDIRECT_STATE = False
    ACCESS_TOKEN_METHOD = "POST"
    DEFAULT_SCOPE = ["openid"]
    EXTRA_DATA = [
        ("id", "id"),
        ("expires_in", "expires"),
    ]

    def user_data(self, access_token, *args, **kwargs):
        """Fetch user data from the userinfo endpoint."""
        return self.get_json(
            self.USER_DATA_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    def get_user_id(self, details, response):
        """
        Return the provider sub as the initial uid.
        This value is replaced with id_persona by the provision_user pipeline
        step before PSA creates the UserSocialAuth link.
        """
        return response.get("sub")

    def get_user_details(self, response):
        """
        identification is the indiv_id used to query the PH API for the full personal data.
        """
        return {
            "identification": response.get("identification", ""),
        }

    def disconnect(self, *args, **kwargs): 
        """
        Override of BaseOAuth2.disconnect to unlink the learner from its indiv_id if associated.
        """
        user = kwargs.get('user', None)
        if user is not None:
            UserIndivId.objects.filter(user=user).delete()
        return super().disconnect(*args, **kwargs)
