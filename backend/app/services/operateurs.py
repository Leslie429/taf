"""Le choix de l'opérateur, numéro par numéro.

Au Bénin, MTN ne couvre pas tout le marché : une tontine réunit des membres
chez plusieurs opérateurs, et un versement doit partir chez celui du
bénéficiaire. L'opérateur ne se choisit donc pas au démarrage de l'application
mais à chaque paiement, d'après le numéro concerné.

**La table des préfixes est une configuration, jamais une constante du code.**
Les plages de numérotation sont attribuées par le régulateur et changent ; les
figer dans les sources garantit qu'elles seront fausses un jour sans que rien
ne le signale.

Et cette résolution reste une approximation : la portabilité des numéros permet
à un abonné de garder son numéro en changeant d'opérateur. Le préfixe donne
alors le mauvais résultat. C'est acceptable ici parce que l'erreur est visible
et rattrapable — l'opérateur refuse l'appel, la transaction échoue, et le rang
d'essai permet de la relancer ailleurs. Un service de production interrogerait
un annuaire de portabilité.
"""

from dataclasses import dataclass

from app.services.momo import MoMoClient


def analyser_prefixes(declaration: str) -> dict[str, tuple[str, ...]]:
    """Lit « mtn:22951,22961;moov:22994 » en table de préfixes par opérateur.

    Une déclaration illisible ne lève pas : elle est ignorée, et la résolution
    retombe sur l'opérateur par défaut. Un réglage mal saisi ne doit pas
    empêcher l'application de démarrer.
    """
    table: dict[str, tuple[str, ...]] = {}
    for bloc in declaration.split(";"):
        code, _, liste = bloc.partition(":")
        code = code.strip()
        if not code or not liste.strip():
            continue
        prefixes = tuple(
            morceau.strip().lstrip("+") for morceau in liste.split(",") if morceau.strip()
        )
        if prefixes:
            table[code] = prefixes
    return table


def normaliser(numero: str) -> str:
    """Ramène un numéro à ses seuls chiffres, indicatif compris."""
    return "".join(caractere for caractere in numero if caractere.isdigit())


@dataclass(frozen=True)
class Operateurs:
    """Les clients disponibles, et la façon d'en choisir un."""

    clients: dict[str, MoMoClient]
    prefixes: dict[str, tuple[str, ...]]
    defaut: str

    def code_pour_numero(self, numero: str) -> str:
        """L'opérateur qui dessert ce numéro.

        Le préfixe le plus long l'emporte : les plages se chevauchent en
        longueur, et « 22961 » doit primer sur « 2296 » quand les deux sont
        déclarés.
        """
        chiffres = normaliser(numero)
        meilleur_code = self.defaut
        meilleure_longueur = 0
        for code, prefixes in self.prefixes.items():
            for prefixe in prefixes:
                if chiffres.startswith(prefixe) and len(prefixe) > meilleure_longueur:
                    meilleur_code, meilleure_longueur = code, len(prefixe)
        return meilleur_code

    def pour_numero(self, numero: str) -> MoMoClient:
        """Le client à utiliser pour ce numéro."""
        return self.pour_code(self.code_pour_numero(numero)) or self.clients[self.defaut]

    def pour_code(self, code: str) -> MoMoClient | None:
        """Le client d'un opérateur donné, ou None s'il n'en existe pas.

        Sert au rapprochement, qui part d'une transaction et de l'opérateur
        qu'elle a consigné, sans plus disposer du numéro.
        """
        return self.clients.get(code)
