# EOL_SSO

Acts as a middleware between apps and the interface of uchileedxlogin and the models of eol_sso_login. In order to work it requires either uchileedxlogin or eol_sso_login to be installed alongside it.
Also implements a custom OAuth2 SSO integration for Open edX. It differs from the standard Open edX flow in several key ways, which required a custom PSA pipeline:

- The uid used to link a Django user to their Uchile account comes from an external API, not the OAuth2 provider's native identifier.
- User profile data (name, email, etc.) is likewise sourced from the external API rather than the OAuth2 login response.
- Account creation is automatic, since user data comes from a the external API, there's no registration form step; standard PSA steps that normally handle that (get_username, create_user, etc.) are replaced.

Two custom steps were added to the pipeline:

- resolve_uid: fetches persona data from the external API using the identification field from the OAuth2 response, and overrides uid with the API's id_persona. Must run before the standard social_user step, since that's what checks whether this uid is already linked to a Django account.
- provision_user: if social_user already found a linked account, just updates its indiv_id link. Otherwise, attempts to match an existing Django account by email, or creates a new one. Email matching excludes any account already linked to this backend.

# Backend registration
Add the custom backend to THIRD_PARTY_AUTH_BACKENDS:
```
THIRD_PARTY_AUTH_BACKENDS:
    - "social_core.backends.google.GoogleOAuth2"
    - "social_core.backends.linkedin.LinkedinOAuth2"
    - "social_core.backends.facebook.FacebookOAuth2"
    - "social_core.backends.azuread.AzureADOAuth2"
    - "common.djangoapps.third_party_auth.appleid.AppleIdAuth"
    - "common.djangoapps.third_party_auth.identityserver3.IdentityServer3"
    - "common.djangoapps.third_party_auth.saml.SAMLAuthBackend"
    - "common.djangoapps.third_party_auth.lti.LTIAuthBackend"
    - "eol_sso.backends.UchileOAuth2Backend"
```

Also the following settings need to be setted on settings/common.py:
```
UCHILE_OAUTH2_AUTHORIZATION_URL = "..."
UCHILE_OAUTH2_ACCESS_TOKEN_URL = "..."
UCHILE_OAUTH2_USER_DATA_URL = "..."
```

# Pipeline configuration
SOCIAL_AUTH_UCHILE_OAUTH2_PIPELINE must be added to lms.yml
```
SOCIAL_AUTH_UCHILE_OAUTH2_PIPELINE:
    - "common.djangoapps.third_party_auth.pipeline.parse_query_params"
    - "social_core.pipeline.social_auth.social_details"
    - "social_core.pipeline.social_auth.social_uid"
    - "social_core.pipeline.social_auth.auth_allowed"
    - "eol_sso.pipeline.resolve_uid"
    - "social_core.pipeline.social_auth.social_user"
    - "eol_sso.pipeline.provision_user"
    - "common.djangoapps.third_party_auth.pipeline.set_pipeline_timeout"
    - "social_core.pipeline.social_auth.associate_user"
    - "social_core.pipeline.social_auth.load_extra_data"
    - "social_core.pipeline.user.user_details"
    - "common.djangoapps.third_party_auth.pipeline.user_details_force_sync"
    - "common.djangoapps.third_party_auth.pipeline.set_logged_in_cookies"
```

## TESTS

This repository includes tests that verify the functionality of the middleware's integration with both uchileedxlogin and eol_sso_login.

**Prepare tests:**

- Install **act** following the instructions in [https://nektosact.com/installation/index.html](https://nektosact.com/installation/index.html)

**Run tests:**
- In a terminal at the root of the project
    ```
    act -W .github/workflows/pythonapp.yml
    ```
