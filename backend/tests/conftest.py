import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.connectors.synthetic import SyntheticConnector
from app.database import build_engine, get_db, initialize_database
from app.main import create_app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        database_path = os.path.join(temporary_directory, "test.db")
        engine = build_engine(f"sqlite:///{database_path}")
        initialize_database(engine)
        TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        settings = Settings(
            database_url=f"sqlite:///{database_path}",
            connector="synthetic",
            allowed_origin="http://127.0.0.1:5181",
        )
        app = create_app(settings=settings, connector=SyntheticConnector())
        app.state.testing_session_factory = TestingSession

        def override_db():
            session = TestingSession()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as test_client:
            yield test_client
        engine.dispose()
