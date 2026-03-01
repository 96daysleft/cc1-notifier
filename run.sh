#!/bin/bash
# Development script for running the Centauri Alert Notifier

echo "🚀 Starting Centauri Alert Notifier (Python)"
echo "📦 Installing dependencies..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

echo "▶️ Starting service..."
python main.py
