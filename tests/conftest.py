import csv
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, DBEvent, get_db
from app.main import app

TEST_DB = "sqlite:///./test_store.db"
engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    csv_path = "test_pos_transactions.csv"
    os.environ["POS_CSV_PATH"] = csv_path
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    with open(csv_path, mode="w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["store_id", "transaction_id", "timestamp", "basket_value_inr"])
        writer.writerow(["STORE_TEST_001", "TXN_991", "2026-03-03T14:40:00Z", "1250.00"])
        writer.writerow(["STORE_TEST_001", "TXN_992", "2026-03-03T14:45:00Z", "650.00"])
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists(csv_path):
        os.remove(csv_path)
    os.environ.pop("POS_CSV_PATH", None)


@pytest.fixture(autouse=True)
def clean_events_table():
    db = TestingSessionLocal()
    db.query(DBEvent).delete()
    db.commit()
    db.close()
    yield


@pytest.fixture
def client():
    return TestClient(app)
