import os, sqlite3, random, time, json, hashlib, hmac
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

DB=os.getenv('DB_PATH','/tmp/acme_mcp.sqlite3')
API_KEY=os.getenv('API_KEY','change-me-before-deployment')
ADMIN_KEY=os.getenv('ADMIN_KEY','change-admin-before-deployment')
app=FastAPI(title='Acme Enterprise MCP Test Harness',version='1.0.0',description='Fictional enterprise APIs for testing Jitterbit MCP tools. All data is synthetic.')

def auth(x_api_key: str=Header(default='')):
    if not hmac.compare_digest(x_api_key,API_KEY) and not hmac.compare_digest(x_api_key,ADMIN_KEY): raise HTTPException(401,'Invalid API key')

def admin(x_admin_key: str=Header(default='')):
    if not hmac.compare_digest(x_admin_key,ADMIN_KEY): raise HTTPException(403,'Administrator key required')

@contextmanager
def db():
    c=sqlite3.connect(DB,timeout=20)
    c.row_factory=sqlite3.Row
    try:
        yield c
        c.commit()
    finally:c.close()

def rows(sql,params=()):
    with db() as c:return [dict(x) for x in c.execute(sql,params).fetchall()]

def one(sql,params=()):
    result=rows(sql,params)
    if not result:raise HTTPException(404,'Record not found')
    return result[0]

def init():
    os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY,name TEXT,region TEXT,email TEXT,credit_limit REAL,status TEXT);
        CREATE TABLE IF NOT EXISTS products(sku TEXT PRIMARY KEY,name TEXT,unit_price REAL,reorder_level INTEGER);
        CREATE TABLE IF NOT EXISTS inventory(sku TEXT,warehouse TEXT,quantity INTEGER,PRIMARY KEY(sku,warehouse));
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,customer_id TEXT,sku TEXT,quantity INTEGER,amount REAL,status TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS invoices(id TEXT PRIMARY KEY,customer_id TEXT,order_id TEXT,amount REAL,currency TEXT,due_date TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY,customer_id TEXT,priority TEXT,status TEXT,subject TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS suppliers(id TEXT PRIMARY KEY,name TEXT,sku TEXT,unit_cost REAL,lead_days INTEGER);
        CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY,order_id TEXT,sku TEXT,warehouse TEXT,quantity INTEGER);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT,detail TEXT,at TEXT);
        CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY,order_id TEXT);
        ''')
        if c.execute('SELECT COUNT(*) FROM customers').fetchone()[0]:return
        seed(c)

def seed(c):
    rng=random.Random(20261015)
    regions=['UK','EMEA','APAC','North America']
    for i in range(1,501):
        name=('Acme Retail UK' if i==1 else f'Customer {i:04d} Trading Ltd')
        c.execute('INSERT INTO customers VALUES(?,?,?,?,?,?)',(f'CUST-{i:04d}',name,regions[(i-1)%4],f'contact{i}@example.org',float(rng.choice([10000,25000,50000,100000])),'active' if i%19 else 'on_hold'))
    for i in range(1,101):
        sku=f'SKU-{i:03d}'
        c.execute('INSERT INTO products VALUES(?,?,?,?)',(sku,f'Enterprise Product {i:03d}',float(15+i*3),40))
        for wh in ['LON','DXB','SIN','NYC','AMS']:
            c.execute('INSERT INTO inventory VALUES(?,?,?)',(sku,wh,rng.randint(0,250)))
    today=datetime.now(timezone.utc)
    for i in range(1,2001):
        cust=f'CUST-{rng.randint(1,500):04d}';sku=f'SKU-{rng.randint(1,100):03d}';qty=rng.randint(1,20)
        price=c.execute('SELECT unit_price FROM products WHERE sku=?',(sku,)).fetchone()[0]
        c.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',(f'ORD-{i:05d}',cust,sku,qty,round(qty*price,2),rng.choice(['fulfilled','pending','cancelled']), (today-timedelta(days=rng.randint(0,180))).isoformat()))
    for i in range(1,501):
        o=c.execute('SELECT customer_id,amount FROM orders WHERE id=?',(f'ORD-{i:05d}',)).fetchone()
        c.execute('INSERT INTO invoices VALUES(?,?,?,?,?,?,?)',(f'INV-{i:05d}',o[0],f'ORD-{i:05d}',o[1],'GBP',(today+timedelta(days=rng.randint(-90,30))).date().isoformat(),rng.choice(['open','open','paid'])))
    for i in range(1,201):
        c.execute('INSERT INTO tickets VALUES(?,?,?,?,?,?)',(f'TKT-{i:05d}',f'CUST-{rng.randint(1,500):04d}',rng.choice(['low','medium','high','critical']),rng.choice(['open','open','resolved']),f'Service issue {i}',(today-timedelta(days=rng.randint(0,30))).isoformat()))
    for i in range(1,101):
        c.execute('INSERT INTO suppliers VALUES(?,?,?,?,?)',(f'SUP-{i:03d}',f'Supplier {i:03d}',f'SKU-{i:03d}',float(10+i*2),rng.randint(2,21)))

@app.on_event('startup')
def startup():init()

@app.get('/health',tags=['System'])
def health():return {'status':'ok','service':'acme-mcp-test-harness','data':'synthetic'}

@app.get('/customers',dependencies=[Depends(auth)],tags=['CRM'])
def search_customers(q:str='',region:Optional[str]=None,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    return {'items':rows('SELECT * FROM customers WHERE (name LIKE ? OR id LIKE ?) AND (? IS NULL OR region=?) ORDER BY id LIMIT ? OFFSET ?',('%'+q+'%','%'+q+'%',region,region,limit,offset)),'limit':limit,'offset':offset}

@app.get('/customers/{customer_id}',dependencies=[Depends(auth)],tags=['CRM'])
def get_customer(customer_id:str):return one('SELECT * FROM customers WHERE id=?',(customer_id,))

@app.get('/customers/{customer_id}/overview',dependencies=[Depends(auth)],tags=['CRM'])
def customer_overview(customer_id:str):
    customer=one('SELECT * FROM customers WHERE id=?',(customer_id,))
    return {'customer':customer,'orders':rows('SELECT * FROM orders WHERE customer_id=? ORDER BY created_at DESC LIMIT 20',(customer_id,)),'invoices':rows('SELECT * FROM invoices WHERE customer_id=?',(customer_id,)),'tickets':rows('SELECT * FROM tickets WHERE customer_id=?',(customer_id,))}

@app.get('/products',dependencies=[Depends(auth)],tags=['Inventory'])
def products(limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
    return {'items':rows('SELECT * FROM products ORDER BY sku LIMIT ? OFFSET ?',(limit,offset))}

@app.get('/inventory/{sku}',dependencies=[Depends(auth)],tags=['Inventory'])
def inventory(sku:str):
    product=one('SELECT * FROM products WHERE sku=?',(sku,))
    locations=rows('SELECT * FROM inventory WHERE sku=?',(sku,))
    return {'product':product,'warehouses':locations,'total_available':sum(x['quantity'] for x in locations)}

@app.get('/orders',dependencies=[Depends(auth)],tags=['ERP'])
def orders(customer_id:Optional[str]=None,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    return {'items':rows('SELECT * FROM orders WHERE (? IS NULL OR customer_id=?) ORDER BY id LIMIT ? OFFSET ?',(customer_id,customer_id,limit,offset))}

@app.get('/orders/{order_id}',dependencies=[Depends(auth)],tags=['ERP'])
def order(order_id:str):return one('SELECT * FROM orders WHERE id=?',(order_id,))

class OrderIn(BaseModel):
    customer_id:str
    sku:str
    quantity:int=Field(gt=0,le=10000)

@app.post('/orders',dependencies=[Depends(auth)],tags=['ERP'],status_code=201)
def create_order(body:OrderIn,idempotency_key:str=Header(default='')):
    if not idempotency_key:raise HTTPException(400,'Idempotency-Key header required')
    with db() as c:
        prior=c.execute('SELECT order_id FROM idempotency WHERE key=?',(idempotency_key,)).fetchone()
        if prior:return dict(c.execute('SELECT * FROM orders WHERE id=?',(prior[0],)).fetchone())
        cust=c.execute('SELECT * FROM customers WHERE id=?',(body.customer_id,)).fetchone()
        product=c.execute('SELECT * FROM products WHERE sku=?',(body.sku,)).fetchone()
        if not cust or not product:raise HTTPException(404,'Customer or product not found')
        if cust['status']!='active':raise HTTPException(409,'Customer account is on hold')
        oid='ORD-'+str(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]+1).zfill(5)
        c.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',(oid,body.customer_id,body.sku,body.quantity,round(body.quantity*product['unit_price'],2),'pending',datetime.now(timezone.utc).isoformat()))
        c.execute('INSERT INTO idempotency VALUES(?,?)',(idempotency_key,oid))
        c.execute('INSERT INTO audit(event,detail,at) VALUES(?,?,?)',('create_order',oid,datetime.now(timezone.utc).isoformat()))
        return dict(c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())

class ReservationIn(BaseModel):
    order_id:str
    warehouse:str

@app.post('/inventory/reservations',dependencies=[Depends(auth)],tags=['Inventory'],status_code=201)
def reserve(body:ReservationIn):
    with db() as c:
        order=c.execute('SELECT * FROM orders WHERE id=?',(body.order_id,)).fetchone()
        if not order:raise HTTPException(404,'Order not found')
        prior=c.execute('SELECT * FROM reservations WHERE order_id=?',(body.order_id,)).fetchone()
        if prior:return dict(prior)
        inv=c.execute('SELECT quantity FROM inventory WHERE sku=? AND warehouse=?',(order['sku'],body.warehouse)).fetchone()
        if not inv:raise HTTPException(404,'Warehouse or SKU not found')
        if inv[0]<order['quantity']:raise HTTPException(409,'Insufficient stock')
        c.execute('UPDATE inventory SET quantity=quantity-? WHERE sku=? AND warehouse=?',(order['quantity'],order['sku'],body.warehouse))
        rid='RES-'+body.order_id
        c.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(rid,body.order_id,order['sku'],body.warehouse,order['quantity']))
        return dict(c.execute('SELECT * FROM reservations WHERE id=?',(rid,)).fetchone())

@app.get('/invoices',dependencies=[Depends(auth)],tags=['Finance'])
def invoices(customer_id:Optional[str]=None,status:Optional[str]=None,overdue_days:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=overdue_days)).date().isoformat()
    return {'items':rows('SELECT * FROM invoices WHERE (? IS NULL OR customer_id=?) AND (? IS NULL OR status=?) AND (status="paid" OR due_date<?) ORDER BY due_date LIMIT ? OFFSET ?',(customer_id,customer_id,status,status,cutoff,limit,offset))}

class InvoiceIn(BaseModel):
    order_id:str

@app.post('/invoices',dependencies=[Depends(auth)],tags=['Finance'],status_code=201)
def create_invoice(body:InvoiceIn):
    with db() as c:
        order=c.execute('SELECT * FROM orders WHERE id=?',(body.order_id,)).fetchone()
        if not order:raise HTTPException(404,'Order not found')
        existing=c.execute('SELECT * FROM invoices WHERE order_id=?',(body.order_id,)).fetchone()
        if existing:return dict(existing)
        if not c.execute('SELECT 1 FROM reservations WHERE order_id=?',(body.order_id,)).fetchone():raise HTTPException(409,'Inventory must be reserved before invoicing')
        iid='INV-'+str(c.execute('SELECT COUNT(*) FROM invoices').fetchone()[0]+1).zfill(5)
        c.execute('INSERT INTO invoices VALUES(?,?,?,?,?,?,?)',(iid,order['customer_id'],body.order_id,order['amount'],'GBP',(datetime.now(timezone.utc)+timedelta(days=30)).date().isoformat(),'open'))
        return dict(c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone())

@app.get('/tickets',dependencies=[Depends(auth)],tags=['Support'])
def tickets(priority:Optional[str]=None,status:Optional[str]=None,limit:int=Query(30,ge=1,le=100)):
    return {'items':rows('SELECT * FROM tickets WHERE (? IS NULL OR priority=?) AND (? IS NULL OR status=?) ORDER BY id LIMIT ?',(priority,priority,status,status,limit))}

class TicketUpdate(BaseModel):
    status:str=Field(pattern='^(open|in_progress|escalated|resolved)$')

@app.patch('/tickets/{ticket_id}',dependencies=[Depends(auth)],tags=['Support'])
def update_ticket(ticket_id:str,body:TicketUpdate):
    one('SELECT * FROM tickets WHERE id=?',(ticket_id,))
    with db() as c:c.execute('UPDATE tickets SET status=? WHERE id=?',(body.status,ticket_id))
    return one('SELECT * FROM tickets WHERE id=?',(ticket_id,))

@app.get('/suppliers',dependencies=[Depends(auth)],tags=['Procurement'])
def suppliers(sku:Optional[str]=None):return {'items':rows('SELECT * FROM suppliers WHERE (? IS NULL OR sku=?)',(sku,sku))}

@app.get('/audit',dependencies=[Depends(admin)],tags=['Administration'])
def audit():return {'items':rows('SELECT * FROM audit ORDER BY id DESC LIMIT 100')}

@app.post('/admin/reset',dependencies=[Depends(admin)],tags=['Administration'])
def reset():
    with db() as c:
        for table in ['customers','products','inventory','orders','invoices','tickets','suppliers','reservations','audit','idempotency']:
            c.execute('DELETE FROM '+table)
        seed(c)
    return {'status':'reset','data':'synthetic'}

@app.get('/test/fault',dependencies=[Depends(auth)],tags=['Fault Injection'])
def fault(mode:str=Query('error',pattern='^(error|timeout|malformed|rate_limit)$'),delay_seconds:float=Query(3,ge=0,le=15)):
    if mode=='timeout':time.sleep(delay_seconds);return {'status':'completed','delay_seconds':delay_seconds}
    if mode=='malformed':return JSONResponse(content={'invalid_shape':['unexpected',None]},status_code=200)
    if mode=='rate_limit':raise HTTPException(429,'Simulated rate limit exceeded',headers={'Retry-After':'10'})
    raise HTTPException(503,'Simulated upstream outage')
