# Acme Enterprise MCP Test Harness

A deployable **synthetic** enterprise REST backend for Jitterbit MCP testing. No commercial CRM or ERP required.

## Contents
- `main.py`: FastAPI CRM, ERP, inventory, finance, support, procurement, fault simulation and admin reset.
- `render.yaml`: Render free-tier Blueprint configuration.
- `requirements.txt`: Python dependencies.
- `test_api.py`: Automated smoke and workflow tests.
- `SCENARIOS.md`: MCP evaluation scenarios and scoring.

## Deploy to Render (free)
1. Create a GitHub repository and upload these files to its root. **Do not commit API keys**.
2. Sign in to [Render](https://dashboard.render.com/) and select **New > Blueprint**. Connect the repository and approve the `render.yaml` configuration.
3. Render generates random `API_KEY` and `ADMIN_KEY` environment values. In the service dashboard, locate the environment settings and securely copy both values. Do not put either key in a public repository, screenshot or AI prompt.
4. Wait for deployment, then visit `https://YOUR-SERVICE.onrender.com/health` and `/docs`.
5. Test an authenticated call:
   ```bash
   curl -H 'x-api-key: YOUR_API_KEY' 'https://YOUR-SERVICE.onrender.com/customers/CUST-0001/overview'
   ```
6. Configure an HTTP/REST API tool in Jitterbit MCP for `GET https://YOUR-SERVICE.onrender.com/customers/{customer_id}` with the required `x-api-key` header. Provide a descriptive tool name (`get_customer`) and required `customer_id` argument. Repeat for other endpoints.
7. Test discovery and execution using your MCP client. Keep `/admin/reset` and `/audit` out of the agent's general-purpose tool catalogue.

**Important:** Render free instances can sleep, restart and lose their local SQLite file. The app seeds synthetic data on startup. Results of performance testing on free hosting are not representative of production infrastructure. Render plan availability and limits can change; verify before deployment.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export API_KEY=local-dev-key ADMIN_KEY=local-admin-key # Windows PowerShell: $env:API_KEY='local-dev-key'
uvicorn main:app --reload
pytest -q
```
Swagger: http://127.0.0.1:8000/docs

## Data
Deterministic seed: 500 customers, 100 products, 500 inventory positions (five warehouses), 2,000 orders, 500 invoices, 200 tickets and 100 suppliers. `CUST-0001` is Acme Retail UK. IDs use `CUST-0001`, `ORD-00001`, `SKU-001`, etc. All data is fictional. Invoice dates are relative to seed time.

## Example API calls
```bash
BASE=https://YOUR-SERVICE.onrender.com
KEY=YOUR_API_KEY
curl -H "x-api-key: $KEY" "$BASE/inventory/SKU-001"
curl -H "x-api-key: $KEY" "$BASE/invoices?status=open&overdue_days=30"
curl -H "x-api-key: $KEY" "$BASE/tickets?priority=critical&status=open"
curl -H "x-api-key: $KEY" -H 'Idempotency-Key: order-demo-1' -H 'Content-Type: application/json' -d '{"customer_id":"CUST-0001","sku":"SKU-001","quantity":2}' "$BASE/orders"
```

## MCP tool recommendations
Start with `get_customer`, `get_customer_overview`, `get_inventory`, `list_orders`, `list_invoices`, `list_tickets`, `get_suppliers`, `create_order`, `reserve_inventory`, `create_invoice`, `update_ticket`, `simulate_fault`.

Give write tools clear descriptions about side effects. Ensure the MCP client seeks user approval before irreversible business actions. The API key is a shared prototype credential, not a role-aware authorization system. Do not expose this prototype to untrusted users or use real personal or financial data.

## Known limitations
- SQLite state is not durable on free Render; concurrent/multi-instance behaviour is not production-grade.
- The mock `malformed` mode returns valid JSON with an unexpected shape, not syntactically invalid JSON.
- Only basic API-key authentication; no per-user roles, OAuth, TLS client authentication or audit correlation IDs.
- Idempotency keys are scoped globally and do not validate request-body equivalence.
- No real rate limiter; the fault endpoint simulates a 429 response.
- Invoice filtering uses a simple overdue predicate; paid invoices may appear when no status filter is supplied. For accurate aged receivables, set `status=open`.
- These are intentional prototype boundaries; test security and performance claims only after hardening.
