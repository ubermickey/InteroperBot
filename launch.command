#!/bin/bash
# InteroperBot — double-click to start
# Requires: .venv created, .env configured with ANTHROPIC_API_KEY

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run setup first:"
    echo "  python -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    read -p "Press Enter to close..."
    exit 1
fi

source .venv/bin/activate

if [ ! -f ".env" ]; then
    echo "No .env file found. Copy .env.example and set your API key:"
    echo "  cp .env.example .env"
    read -p "Press Enter to close..."
    exit 1
fi

echo "Starting InteroperBot..."
python bot.py

read -p "Bot stopped. Press Enter to close..."
