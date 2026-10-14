from contextvars import ContextVar


_requete_courante = ContextVar(
    "audit_requete_courante",
    default=None,
)


def get_current_request():
    return _requete_courante.get()


class AuditRequestMiddleware:
    """
    Rend la requête courante accessible aux signaux
    afin d’identifier l’utilisateur responsable
    d’une création, modification ou suppression.
    """

    def __init__(
        self,
        get_response,
    ):
        self.get_response = get_response

    def __call__(
        self,
        request,
    ):
        jeton = _requete_courante.set(
            request
        )

        try:
            return self.get_response(
                request
            )

        finally:
            _requete_courante.reset(
                jeton
            )
