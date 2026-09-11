import pytest
from app import app, db, users_col, products_col, blocks_col, transactions_col
import bcrypt

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    # Use test db
    db.client.drop_database('authchain_test')
    test_db = db.client['authchain_test']
    
    with app.test_client() as client:
        yield client

def test_manufacture_to_customer_flow(client):
    pass
