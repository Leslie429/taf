"""Données : corrige le nom du compte de démonstration (« Léslie » → « Leslie »).

Le script de démonstration avait semé le nom avec un accent fautif, et la
démonstration en ligne l'affiche depuis. Resemer la base de production
effacerait la tontine de démonstration ; une migration, jouée au démarrage du
conteneur, corrige la ligne sans rien toucher d'autre.

La mise à jour est conditionnelle — même téléphone et ancien nom exact — : sur
une base où ce compte n'existe pas, ou a été renommé depuis, elle ne fait rien.

Revision ID: 0007
Revises: 0006
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TELEPHONE_DEMO = "+22901691004"
ANCIEN_NOM = "Léslie Tokponto"
NOUVEAU_NOM = "Leslie Tokponto"


def _renommer(de: str, vers: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE users SET full_name = :vers "
            "WHERE phone = :telephone AND full_name = :de"
        ),
        {"vers": vers, "de": de, "telephone": TELEPHONE_DEMO},
    )


def upgrade() -> None:
    _renommer(ANCIEN_NOM, NOUVEAU_NOM)


def downgrade() -> None:
    _renommer(NOUVEAU_NOM, ANCIEN_NOM)
