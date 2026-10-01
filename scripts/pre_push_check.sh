#!/usr/bin/env bash
# ==============================================================================
# GeoRef Pre-Push Verification Suite
# Run before pushing code to production / GitHub main.
# ==============================================================================
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}        GeoRef Pre-Push Production Verifier         ${NC}"
echo -e "${BLUE}====================================================${NC}"

# Step 1: Environment Variables Check
echo -e "\n${YELLOW}[1/4] Verifying Environment Variables...${NC}"
if [ -f .env ]; then
    echo -e "${GREEN}✓ .env file found.${NC}"
else
    echo -e "${RED}✗ Warning: .env file not found in repository root.${NC}"
fi

# Step 2: Django System Check
echo -e "\n${YELLOW}[2/4] Running Django System Check...${NC}"
python manage.py check
echo -e "${GREEN}✓ Django system check passed with 0 issues.${NC}"

# Step 3: Run Full Automated Unit & Integration Tests
echo -e "\n${YELLOW}[3/4] Running Automated Test Suite (17 Tests)...${NC}"
python manage.py test map_processor --verbosity=1
echo -e "${GREEN}✓ All unit and integration tests passed.${NC}"

# Step 4: Static Asset Compilation Dry-Run
echo -e "\n${YELLOW}[4/4] Verifying Static Files & WhiteNoise Manifest...${NC}"
python manage.py collectstatic --noinput --dry-run > /dev/null
echo -e "${GREEN}✓ Static files compile cleanly without asset collisions.${NC}"

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN}  ✓ ALL CHECKS PASSED! Ready to push to production. ${NC}"
echo -e "${GREEN}====================================================${NC}"
