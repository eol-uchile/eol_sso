def plugin_settings(settings):
    settings.SSOLOGIN_UCHILE_KEY = 'SSOLOGIN_UCHILE_KEY'
    settings.LMS_ROOT_URL =  'http://localhost:8000'
    settings.BASE_EOL_SSO_API_URL = 'https://api.example.cl/'
    settings.UCHILE_OAUTH2_AUTHORIZATION_URL = 'https://api.example.cl/'
    settings.UCHILE_OAUTH2_ACCESS_TOKEN_URL = 'https://api.example.cl/'
    settings.UCHILE_OAUTH2_USER_DATA_URL = 'https://api.example.cl/'
    if "eol_sso.backends.UchileOAuth2Backend" not in settings.AUTHENTICATION_BACKENDS:
        settings.AUTHENTICATION_BACKENDS.append("eol_sso.backends.UchileOAuth2Backend")
    settings.SOCIAL_AUTH_UCHILE_OAUTH2_PIPELINE = [
        "common.djangoapps.third_party_auth.pipeline.parse_query_params",
        "social_core.pipeline.social_auth.social_details",
        "social_core.pipeline.social_auth.social_uid",
        "social_core.pipeline.social_auth.auth_allowed",
        "eol_sso.pipeline.resolve_uid",
        "social_core.pipeline.social_auth.social_user",
        "eol_sso.pipeline.provision_user",
        "common.djangoapps.third_party_auth.pipeline.set_pipeline_timeout",
        "social_core.pipeline.social_auth.associate_user",
        "social_core.pipeline.social_auth.load_extra_data",
        "social_core.pipeline.user.user_details",
        "common.djangoapps.third_party_auth.pipeline.user_details_force_sync",
        "common.djangoapps.third_party_auth.pipeline.set_logged_in_cookies",
    ]
