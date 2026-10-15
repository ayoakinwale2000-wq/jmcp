import os
os.environ['DB_PATH']='/tmp/acme_mcp_pytest.sqlite3'
os.environ['API_KEY']='test-key'
os.environ['ADMIN_KEY']='admin-test-key'
from fastapi.testclient import TestClient
from main import app, init
import pytest

@pytest.fixture
def client():
    if os.path.exists(os.environ['DB_PATH']):os.unlink(os.environ['DB_PATH'])
    init()
    with TestClient(app) as c:yield c

def test_auth(client):
    assert client.get('/customers').status_code==401
    assert client.get('/customers/CUST-0001',headers={'x-api-key':'test-key'}).status_code==200

def test_order_to_cash(client):
    h={'x-api-key':'test-key','Idempotency-Key':'run-001'}
    body={'customer_id':'CUST-0001','sku':'SKU-001','quantity':2}
    a=client.post('/orders',headers=h,json=body)
    assert a.status_code==201
    oid=a.json()['id']
    assert client.post('/orders',headers=h,json=body).json()['id']==oid
    assert client.post('/invoices',headers=h,json={'order_id':oid}).status_code==409
    assert client.post('/inventory/reservations',headers=h,json={'order_id':oid,'warehouse':'LON'}).status_code==201
    assert client.post('/invoices',headers=h,json={'order_id':oid}).status_code==201

def test_faults(client):
    h={'x-api-key':'test-key'}
    assert client.get('/test/fault?mode=rate_limit',headers=h).status_code==429
    assert client.get('/test/fault?mode=error',headers=h).status_code==503

def test_reset(client):
    assert client.post('/admin/reset',headers={'x-admin-key':'admin-test-key'}).status_code==200
    assert client.get('/customers/CUST-0001',headers={'x-api-key':'test-key'}).status_code==200
