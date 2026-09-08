from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Type ENUM PostgreSQL stockant les *valeurs* du StrEnum, pas les noms.

    Par défaut SQLAlchemy persiste `GroupStatus.DRAFT` sous la forme "DRAFT" ;
    on veut "draft", ce que consomme le front et ce que lisent les requêtes SQL
    écrites à la main.
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        native_enum=True,
    )
