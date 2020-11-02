from django.utils.translation import gettext_lazy as _

from drf_spectacular.extensions import OpenApiAuthenticationExtension

from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import (
    BaseAuthentication, get_authorization_header
)
from rest_framework.exceptions import AuthenticationFailed

from baserow.core.exceptions import UserNotInGroupError
from baserow.contrib.database.tokens.handler import TokenHandler
from baserow.contrib.database.tokens.exceptions import TokenDoesNotExist


class TokenAuthentication(BaseAuthentication):
    """
    Authentication backend that check if a token authorization is provided and if so
    if checks if the provided key exists.
    """

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != b'token':
            return None

        if len(auth) == 1:
            msg = _('Invalid token header. No token provided.')
            raise AuthenticationFailed({
                'detail': msg,
                'error': 'ERROR_INVALID_TOKEN_HEADER'
            })
        elif len(auth) > 2:
            msg = _('Invalid token header. Token string should not contain spaces.')
            raise AuthenticationFailed({
                'detail': msg,
                'error': 'ERROR_INVALID_TOKEN_HEADER'
            })

        decoded_key = auth[1].decode(HTTP_HEADER_ENCODING)
        handler = TokenHandler()

        try:
            token = handler.get_by_key(decoded_key)
        except UserNotInGroupError:
            msg = _('The token\'s user does not belong to the group anymore.')
            raise AuthenticationFailed({
                'detail': msg,
                'error': 'ERROR_TOKEN_GROUP_MISMATCH'
            })
        except TokenDoesNotExist:
            msg = _('The provided token does not exist.')
            raise AuthenticationFailed({
                'detail': msg,
                'error': 'ERROR_TOKEN_DOES_NOT_EXIST'
            })

        request.user_token = token
        return token.user, token


class JSONWebTokenAuthenticationExtension(OpenApiAuthenticationExtension):
    target_class = 'baserow.contrib.database.api.tokens.authentications.' \
                   'TokenAuthentication'
    name = 'Token'
    match_subclasses = True
    priority = -1

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'Token your_token',
        }
