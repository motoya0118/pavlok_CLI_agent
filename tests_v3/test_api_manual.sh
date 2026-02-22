#!/bin/bash
# Manual API Test Script for Oni System v0.3
# Run this while FastAPI server is running

BASE_URL="${1:-http://localhost:8000}"

echo "=========================================="
echo "E2E API Test - Oni System v0.3"
echo "Target: $BASE_URL"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Helper functions
test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
    fi
}

# ============================================================================
# Test 1: Health Check
# ============================================================================
echo "[Test 1] Health Check"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/health")
STATUS=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

echo "  Status: $STATUS"
echo "  Response: $BODY"

if [ "$STATUS" = "200" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Test 2: Health returns valid JSON
# ============================================================================
echo "[Test 2] Health returns valid JSON with required fields"
RESPONSE=$(curl -s "$BASE_URL/health")

STATUS=$(echo "$RESPONSE" | jq -r '.status' 2>/dev/null)
VERSION=$(echo "$RESPONSE" | jq -r '.version' 2>/dev/null)

echo "  Status: $STATUS"
echo "  Version: $VERSION"

if [ "$STATUS" = "ok" ] && [ "$VERSION" = "0.3.0" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Test 3: Unknown endpoint returns 404
# ============================================================================
echo "[Test 3] Unknown endpoint returns 404"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/unknown")

echo "  Status: $STATUS"

if [ "$STATUS" = "404" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Test 4: Slack command without signature returns 401
# ============================================================================
echo "[Test 4] Slack command without signature returns 401"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -d "command=/base_commit" \
    -d "user_id=U03JBULT484" \
    "$BASE_URL/slack/command")

echo "  Status: $STATUS"

if [ "$STATUS" = "401" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Test 5: Interactive endpoint without signature returns 401
# ============================================================================
echo "[Test 5] Interactive endpoint without signature returns 401"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"type":"block_actions"}' \
    "$BASE_URL/slack/interactive")

echo "  Status: $STATUS"

if [ "$STATUS" = "401" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Test 6: Internal endpoint without secret returns 401
# ============================================================================
echo "[Test 6] Internal endpoint without secret returns 401"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "$BASE_URL/internal/execute/plan")

echo "  Status: $STATUS"

if [ "$STATUS" = "401" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Test 7: Internal config endpoint without secret returns 401
# ============================================================================
echo "[Test 7] Internal config endpoint without secret returns 401"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "$BASE_URL/internal/config/PAVLOK_VALUE_PUNISH")

echo "  Status: $STATUS"

if [ "$STATUS" = "401" ]; then
    test_result 0
else
    test_result 1
fi
echo ""

# ============================================================================
# Summary
# ============================================================================
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "Total: $((PASSED + FAILED))"
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
