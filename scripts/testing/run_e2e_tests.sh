#!/bin/bash

echo "======================================="
echo "Running End-to-End Tests"
echo "======================================="

# Check if services are running
echo "Checking if services are running..."
if ! docker compose ps | grep -q "Up"; then
    echo "Services are not running. Please run ./deploy.sh first."
    exit 1
fi

# Wait for services to be healthy
echo "Waiting for services to be fully ready..."
sleep 5

# Run e2e tests
echo "Running e2e tests..."
source venv/bin/activate || python3 -m venv venv && source venv/bin/activate

# Install test dependencies if needed
pip install pytest httpx

# Run the tests
python -m pytest tests/e2e/test_e2e_workflow.py -v

echo "======================================="
echo "E2E Tests Completed"
echo "======================================="