#!/bin/bash
# EC2 setup script for Kronos Trader
# Run this after SSHing into the g5.xlarge instance
set -euo pipefail

echo "=== Kronos Trader EC2 Setup ==="

# Wait for user data to finish (docker install, nvidia drivers)
echo "Waiting for Docker to be ready..."
while ! docker info >/dev/null 2>&1; do
  echo "  Docker not ready yet, waiting 10s..."
  sleep 10
done
echo "Docker is ready!"

# Check NVIDIA GPU
echo "Checking GPU..."
nvidia-smi 2>/dev/null && echo "GPU detected!" || echo "WARNING: GPU not available, will use CPU mode"

# Clone the repo
APP_DIR=/home/ec2-user/kronos-trader
if [ -d "$APP_DIR" ]; then
  echo "Updating existing repo..."
  cd "$APP_DIR"
  git pull
else
  echo "Cloning repo..."
  cd /home/ec2-user
  git clone https://github.com/JonChristensen/kronos-trader.git
  cd "$APP_DIR"
fi

# Fetch secrets from AWS Secrets Manager
echo "Fetching secrets from Secrets Manager..."
REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/region)

# Get DB credentials
DB_SECRET_ID=$(aws secretsmanager list-secrets --region "$REGION" \
  --query "SecretList[?Name.starts_with(@, 'KtData')].Name | [0]" --output text 2>/dev/null || echo "")

if [ -n "$DB_SECRET_ID" ] && [ "$DB_SECRET_ID" != "None" ]; then
  DB_SECRET=$(aws secretsmanager get-secret-value --secret-id "$DB_SECRET_ID" --region "$REGION" --query SecretString --output text)
  DB_USER=$(echo "$DB_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin)['username'])")
  DB_PASS=$(echo "$DB_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")
  DB_HOST=$(echo "$DB_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin)['host'])")
  DB_PORT=$(echo "$DB_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin).get('port', '5432'))")
  echo "  DB credentials loaded from Secrets Manager"
else
  echo "  WARNING: DB secret not found, using defaults"
  DB_USER="kt"
  DB_PASS="kt"
  DB_HOST="localhost"
  DB_PORT="5432"
fi

# Get app secrets (Alpaca keys, auth tokens)
APP_SECRET=$(aws secretsmanager get-secret-value --secret-id "kt/app-secrets" --region "$REGION" --query SecretString --output text 2>/dev/null || echo '{}')
ALPACA_KEY=$(echo "$APP_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin).get('alpaca_api_key', ''))")
ALPACA_SECRET=$(echo "$APP_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin).get('alpaca_secret_key', ''))")
EXEC_AUTH=$(echo "$APP_SECRET" | python3 -c "import sys,json; print(json.load(sys.stdin).get('exec_auth_token', 'change-me'))")

echo "  App secrets loaded"

# Determine GPU availability
if nvidia-smi >/dev/null 2>&1; then
  KRONOS_DEVICE="cuda"
else
  KRONOS_DEVICE="cpu"
fi

# Generate .env file
cat > "$APP_DIR/.env" <<ENVEOF
# Alpaca API credentials
ALPACA_API_KEY=${ALPACA_KEY}
ALPACA_SECRET_KEY=${ALPACA_SECRET}
ALPACA_PAPER=true
ALPACA_DATA_FEED=iex

# Execution service
EXEC_DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/kt_execution
EXEC_HOST=0.0.0.0
EXEC_PORT=8001
EXEC_AUTH_TOKEN=${EXEC_AUTH}
EXEC_MAX_POSITION_DOLLARS=1000
EXEC_MAX_DAILY_LOSS_DOLLARS=200
EXEC_MAX_TRADE_DOLLARS=500
EXEC_MAX_TRADES_PER_HOUR=50

# Agent service
AGENT_EXECUTION_SERVICE_URL=http://execution:8001
AGENT_AUTH_TOKEN=${EXEC_AUTH}
AGENT_DAILY_CYCLE_TIME=09:35
AGENT_INTRADAY_INTERVAL_SECONDS=3600
AGENT_EDGE_THRESHOLD=0.005
AGENT_CONFIDENCE_THRESHOLD=0.4

# Kronos model
KRONOS_MODEL_NAME=NeoQuasar/Kronos-small
KRONOS_DEVICE=${KRONOS_DEVICE}
KRONOS_SAMPLE_COUNT=20

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
ENVEOF

echo "  .env file written"

# Create docker-compose override for production (uses RDS instead of local postgres)
cat > "$APP_DIR/docker-compose.prod.yml" <<COMPEOF
services:
  execution:
    build:
      context: .
      dockerfile: Dockerfile.execution
    ports:
      - "8001:8001"
    env_file: .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/api/v1/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  agent:
    build:
      context: .
      dockerfile: Dockerfile.agent.gpu
    env_file: .env
    environment:
      - AGENT_EXECUTION_SERVICE_URL=http://execution:8001
      - KRONOS_DEVICE=${KRONOS_DEVICE}
    depends_on:
      execution:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
COMPEOF

echo "  docker-compose.prod.yml written"

# Build Docker images
echo "Building Docker images..."
docker compose -f docker-compose.prod.yml build

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Update Alpaca keys in Secrets Manager (kt/app-secrets)"
echo "  2. Run migrations: docker compose -f docker-compose.prod.yml run --rm execution alembic upgrade head"
echo "  3. Start services: docker compose -f docker-compose.prod.yml up -d"
echo "  4. Check dashboard at: http://<ALB-URL>"
echo ""
