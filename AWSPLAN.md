# AWS Deployment Plan — Harry's Risers

## Architecture recap

```
EventBridge (rate 30 min) -> CollectorFunction (Lambda) -> Reddit RSS + StockTwits + yfinance -> DynamoDB
API Gateway -> ApiFunction (Lambda, Flask) -> DynamoDB / yfinance -> JSON
Angular (GitHub Pages) <- GET /api/stocks, GET /api/historical
```

Two Lambda container image functions, one HTTP API Gateway, one DynamoDB table, one EventBridge schedule.
All infrastructure is defined in `backend/template.yaml` (AWS SAM).

---

## Phase 0 — Rate limiting and billing protection (do this first)

Rate limiting lives at the **AWS infrastructure level**, not in Python. Flask can't
stop many Lambda instances from running in parallel — only AWS controls can do that.
These are already configured in `backend/template.yaml`:

| Control | Setting | What it prevents |
|---|---|---|
| `ReservedConcurrentExecutions: 5` | Max 5 parallel Lambda invocations per function | Runaway parallel executions from a traffic spike or bug |
| `ThrottlingBurstLimit: 20` | Max 20 concurrent API requests at any instant | Sudden floods at the API Gateway layer |
| `ThrottlingRateLimit: 10` | Max 10 sustained requests/second | Sustained scraping or abuse |

These deploy automatically with `sam deploy` — no manual console steps needed.

### Billing alert (set this up in the AWS console after creating your account)

This is the safety net that catches anything the infra limits miss.

1. Go to **AWS Console → Billing → Budgets → Create budget**
2. Choose **"Cost budget"**
3. Set amount: **$5/month** (you should never hit this at this scale)
4. Add an alert at **80% of budget** → enter your email
5. Create the budget

You will receive an email if charges approach $5 in any calendar month. At normal
traffic this app costs effectively $0/month (all services are free-tier eligible).

---

## Phase 1 — Install prerequisites

### 1. Docker Desktop
Required to build Lambda container images (yfinance pulls pandas/numpy — too large for a zip).

Download from https://www.docker.com/products/docker-desktop/
Choose "Mac with Apple Silicon" or "Mac with Intel chip" as appropriate.
Install and **launch Docker** — the daemon must be running before `sam build`.

### 2. AWS CLI + SAM CLI
```bash
brew install awscli
brew install aws-sam-cli
```

### 3. AWS account and credentials
1. Create an AWS account at https://aws.amazon.com if you don't have one.
2. In the AWS console go to **IAM → Users → Create user**.
3. Attach the `AdministratorAccess` policy (fine for a personal project).
4. Under **Security credentials → Create access key** → choose "CLI" use case.
5. Copy the Access Key ID and Secret Access Key.

Configure the CLI:
```bash
aws configure
# AWS Access Key ID:     <paste>
# AWS Secret Access Key: <paste>
# Default region:        us-east-1
# Default output format: json
```

### 4. Verify everything is ready
```bash
docker --version
aws sts get-caller-identity   # returns your account ID — confirms auth works
sam --version
```

All three must succeed before moving to Phase 2.

---

## Phase 2 — Build and deploy

```bash
cd backend
sam build                 # builds Docker images for both Lambda functions
sam deploy --guided       # first-time walkthrough; saves answers to samconfig.toml
```

Parameters to set during `sam deploy --guided`:
- **Stack name:** `harrys-risers` (or any name you like)
- **Region:** `us-east-1` (match what you set in `aws configure`)
- **CorsOrigins:** `https://cmathews33.github.io`
- **RedditSource:** `rss` (default — leave as-is)
- Allow SAM to create IAM roles: **yes**
- Save config to samconfig.toml: **yes** (future deploys just need `sam deploy`)

### After deploy
The stack outputs will print an `ApiUrl` — copy it. It looks like:
```
https://abc123xyz.execute-api.us-east-1.amazonaws.com
```

---

## Phase 3 — Wire the frontend to the deployed API

Update `my-app/src/environments/environment.prod.ts` with the real URL:
```typescript
export const environment = {
  apiBaseUrl: 'https://abc123xyz.execute-api.us-east-1.amazonaws.com',
};
```

Rebuild and redeploy the Angular app to GitHub Pages:
```bash
cd my-app
export PATH="$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"
node_modules/.bin/ng build
node_modules/.bin/ng deploy
```

---

## Phase 4 — Verify end-to-end

```bash
# Hit the deployed API directly
curl https://abc123xyz.execute-api.us-east-1.amazonaws.com/api/health
curl https://abc123xyz.execute-api.us-east-1.amazonaws.com/api/stocks

# Check DynamoDB was populated by the collector
aws dynamodb scan --table-name harrys-risers --max-items 5
```

Then open https://cmathews33.github.io in a browser and confirm the live table loads from the API.

---

## Future deploys

After the first deploy, `samconfig.toml` is saved in `backend/`. Subsequent deploys are just:
```bash
cd backend
sam build && sam deploy
```

---

## Cost estimate

All services used are free-tier eligible for a low-traffic personal project:
- Lambda: 1M requests/month free
- DynamoDB: 25 GB storage + 25 read/write capacity units free
- API Gateway: 1M HTTP API calls/month free
- EventBridge: 14M events/month free

Running cost at this scale: effectively $0/month.
