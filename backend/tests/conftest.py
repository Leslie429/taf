import os
from collections.abc import Generator

import pytest

# Doit précéder tout import de l'application : la configuration est lue au chargement.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://tontine:tontine@localhost:5432/tontine_test"
)
os.environ.setdefault("JWT_SECRET", "secret-de-test")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.api.deps import get_current_user, get_operateurs  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.momo import FakeMoMoClient  # noqa: E402
from app.services.operateurs import Operateurs  # noqa: E402

engine = create_engine(settings.database_url, future=True)
TestSession = sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Generator[None, None, None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Chaque test tourne dans une transaction annulée à la fin : aucun état ne fuit."""
    connection = engine.connect()
    transaction = connection.begin()
    # create_savepoint : un db.commit() dans une route relâche un point de
    # sauvegarde, et le rollback final annule bien tout ce que le test a écrit.
    session = Session(bind=connection, join_transaction_mode="create_savepoint", future=True)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def momo() -> FakeMoMoClient:
    return FakeMoMoClient()


@pytest.fixture
def reseau(momo: FakeMoMoClient) -> Operateurs:
    """Un réseau dont tous les opérateurs sont le même double.

    Le double est enregistré sous « fake » — le code qu'il déclare lui-même —
    et sous les codes des opérateurs réels, pour que les tests puissent
    attribuer une transaction à MTN tout en gardant la main sur ses réponses.
    """
    return Operateurs(
        clients={"fake": momo, "mtn_momo": momo, "moov": momo},
        prefixes={},
        defaut="mtn_momo",
    )


@pytest.fixture
def client(
    db: Session, reseau: Operateurs
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_operateurs] = lambda: reseau
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db: Session):
    from app.core.security import hash_password

    counter = {"n": 0}

    def _make(full_name: str = "Membre") -> User:
        counter["n"] += 1
        user = User(
            phone=f"+2290100000{counter['n']:02d}",
            full_name=full_name,
            hashed_password=hash_password("motdepasse123"),
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def auth_as(client: TestClient):
    from app.core.security import create_token

    def _auth(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user
        client.headers["Authorization"] = f"Bearer {create_token(user.id, 'access')}"

    return _auth
