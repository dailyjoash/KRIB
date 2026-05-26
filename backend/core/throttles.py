from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class IdentityRateThrottle(SimpleRateThrottle):
    scope = None

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class LoginRateThrottle(IdentityRateThrottle):
    scope = "login"


class RegisterRateThrottle(IdentityRateThrottle):
    scope = "register"


class PasswordResetRateThrottle(IdentityRateThrottle):
    scope = "password_reset"


class PasswordResetConfirmThrottle(SimpleRateThrottle):
    """Throttle the password-reset confirmation endpoint by UID+IP.

    Keying off the UID prevents one attacker from burning the IP allowance
    against many tokens, while still throttling raw IP abuse against a
    single UID. Falls back to IP if the UID is missing.
    """

    scope = "password_reset_confirm"

    def get_cache_key(self, request, view):
        uid = ""
        if hasattr(request, "data"):
            try:
                uid = (request.data or {}).get("uid") or ""
            except Exception:
                uid = ""
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{uid}:{ident}" if uid else ident,
        }


class STKInitiateRateThrottle(IdentityRateThrottle):
    scope = "stk_initiate"


class OTPRateThrottle(AnonRateThrottle):
    scope = "otp_verify"


class TokenObtainRateThrottle(IdentityRateThrottle):
    # Wired onto /api/token/ so the SimpleJWT endpoint cannot be used as a
    # rate-limit bypass against /api/auth/login/'s slower 5/min throttle.
    scope = "token_obtain"
