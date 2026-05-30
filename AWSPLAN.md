# AWS Deployment Plan — Harry's Risers

## Architecture recap

```
EventBridge (15 min during US market hours, hourly otherwise)
  -> CollectorFunction (Lambda) -> Reddit RSS + yfinance -> DynamoDB (live + daily history)
API Gateway -> ApiFunction (Lambda, Flask) -> DynamoDB (live + accumulated history) -> JSON
Angular (GitHub Pages) <- GET /api/stocks, GET /api/historical
```

Two Lambda container image functions, one HTTP API Gateway, one DynamoDB table, two
EventBridge schedules (market-hours + off-hours). All infrastructure is defined in
`backend/template.yaml` (AWS SAM).

---

## Phase 0 — Rate limiting and billing protection (do this first)

Rate limiting lives at the **AWS infrastructure level**, not in Python. Flask can't
stop many Lambda instances from running in parallel — only AWS controls can do that.
These are already configured in `backend/template.yaml`:

| Control | Setting | What it prevents |
|---|---|---|
| `ThrottlingBurstLimit: 20` | Max 20 concurrent API requests at any instant | Sudden floods at the API Gateway layer |
| `ThrottlingRateLimit: 10` | Max 10 sustained requests/second | Sustained scraping or abuse |

> **Note:** `ReservedConcurrentExecutions` was removed from the template. New AWS
> accounts require at least 10 unreserved concurrent executions — setting 5 per
> function (10 total) caused `CREATE_FAILED` on first deploy. API Gateway throttling
> is sufficient cost protection for this project.

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

### 1. Docker
Required to build Lambda container images (yfinance pulls pandas/numpy — too large for a zip).

**Option A — Docker Desktop** (requires macOS 12+):
Download from https://www.docker.com/products/docker-desktop/
Choose "Mac with Apple Silicon" or "Mac with Intel chip" as appropriate.

**Option B — Colima** (lightweight alternative, works on older macOS, confirmed working on Ventura 13.6.9):
```bash
brew install colima docker
colima start
export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"
```
Add the `export` line to `~/.zshrc` so it persists across sessions. Run
`colima start` once each time you restart your machine before running `sam build`.

Either way, verify Docker is working before proceeding:
```bash
docker ps   # should return an empty list, no error
```

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

Always run `sam build` before `sam deploy` after any code or template change —
`sam deploy` alone does not rebuild the Docker images.

Parameters to set during `sam deploy --guided`:
- **Stack name:** `harrys-risers` (or any name you like)
- **Region:** `us-east-1` (match what you set in `aws configure`)
- **CorsOrigins:** `https://cmathews33.github.io`
- **RedditSource:** `rss` (default — leave as-is)
- Allow SAM to create IAM roles: **yes**
- Save config to samconfig.toml: **yes** (future deploys just need `sam build && sam deploy`)

### After deploy
The stack outputs will print an `ApiUrl` — copy it. It looks like:
```
https://abc123xyz.execute-api.us-east-1.amazonaws.com
```

### What SAM creates in AWS
| Resource | Where to find it in console |
|---|---|
| **ApiFunction** Lambda | Lambda → Functions |
| **CollectorFunction** Lambda | Lambda → Functions |
| **AppHttpApi** (HTTP API Gateway) | API Gateway → APIs — invoke URL = your ApiUrl |
| **DataTable** (DynamoDB) | DynamoDB → Tables |
| **EventBridge schedules** (market-hours 15 min + off-hours hourly) | EventBridge → Schedules |
| **ECR repositories** (Docker images) | ECR → Repositories |
| **IAM execution roles** | IAM → Roles |

DynamoDB will be empty until the first CollectorFunction run (within 15 min during
market hours, otherwise within the hour).

### Seed historical price history (run once after the first deploy)
`/api/historical` reads accumulated daily snapshots, which only grow going forward.
Backfill ~1y of real daily prices so the historical view works immediately:
```bash
cd backend
DYNAMODB_TABLE=harrys-risers AWS_DEFAULT_REGION=us-east-1 \
  .venv/bin/python -m scripts.backfill_history
```
(Uses your AWS credentials to write directly to the deployed table. Omit
`DYNAMODB_ENDPOINT` to target real AWS.) Mention/sentiment history then accumulates
from each scheduled collector run.

### Deploy gotchas encountered
- **`ServerlessHttpApi` is a reserved SAM logical ID** — causes a warning and
  unexpected behaviour. The explicit API resource is named `AppHttpApi` in
  `template.yaml`.
- **`ReservedConcurrentExecutions: 5` fails on new accounts** — AWS requires
  ≥10 unreserved executions; two functions × 5 = 10 reserved leaves 0 unreserved.
  Removed from the template; API Gateway throttling is sufficient.
- **`ROLLBACK_COMPLETE` stack cannot be updated** — if a deploy fails and rolls
  back, delete the stack first before redeploying:
  ```bash
  aws cloudformation delete-stack --stack-name harrys-risers
  # wait ~60s, confirm gone:
  aws cloudformation describe-stacks --stack-name harrys-risers
  # then:
  sam build && sam deploy
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

## Monitoring and staleness detection

The CollectorFunction runs every 15 min during US market hours (hourly otherwise).
If yfinance gets throttled by Yahoo Finance, it fails silently — the API serves
stale DynamoDB data rather than crashing.

**Checking for stale data (in order of speed):**
1. Hit `/api/stocks` — inspect the top-level `refreshedAt` field. If it is hours old
   during market hours, the collector is failing.
2. **DynamoDB console** → Explore items → filter `pk = LIVE`, `sk = latest` →
   check the `refreshedAt` field.
3. **CloudWatch Logs** → Log groups → `/aws/lambda/harrys-risers-CollectorFunction-XXXX`
   → open the latest stream → look for `429` or HTTP errors.

The ApiFunction only runs on request — zero cost or activity when the app is idle.
The CollectorFunction runs ~15×/day off-hours plus every 15 min during market hours
(~30 weekday market-hours runs), well within the Lambda free tier.

---

## Cost estimate

All services used are free-tier eligible for a low-traffic personal project:
- Lambda: 1M requests/month free
- DynamoDB: 25 GB storage + 25 read/write capacity units free
- API Gateway: 1M HTTP API calls/month free
- EventBridge: 14M events/month free

Running cost at this scale: effectively $0/month.
