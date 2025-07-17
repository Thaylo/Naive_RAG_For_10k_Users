#!/bin/bash

# Activate virtual environment and run tests
echo "Running tests..."
source venv/bin/activate || python3 -m venv venv && source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-xdist pytest-asyncio pytest-cov

# Run tests
python -m pytest tests/ -v

echo "Tests completed!"