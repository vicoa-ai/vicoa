#!/bin/bash

# Database initialization script using Alembic migrations
# This script will upgrade the database to the latest migration version

set -e
set -o pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🗄️  Initializing database with Alembic migrations...${NC}"

# Change to the shared directory where alembic.ini is located
cd "$(dirname "$0")/../src/shared"

# A migration gives up on a lock after MIGRATION_LOCK_TIMEOUT (see env.py) and
# rolls back whole, so it is safe to try again: a table held by a short
# transaction is free a moment later. Any other failure is not retried.
attempts="${MIGRATION_ATTEMPTS:-5}"
log="$(mktemp)"
trap 'rm -f "$log"' EXIT

for attempt in $(seq 1 "$attempts"); do
    # Run alembic upgrade head to apply all pending migrations
    if alembic upgrade head 2>&1 | tee "$log"; then
        echo -e "${GREEN}✅ Database successfully migrated to latest version${NC}"
        exit 0
    fi
    if ! grep -q "lock timeout" "$log"; then
        break
    fi
    if [ "$attempt" -lt "$attempts" ]; then
        echo -e "${YELLOW}⏳ A table was locked (attempt ${attempt}/${attempts}); retrying in 10s${NC}"
        sleep 10
    fi
done

echo -e "${RED}❌ Error running Alembic migrations${NC}"
exit 1
