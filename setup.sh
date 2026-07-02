#!/usr/bin/env bash
set -e

echo "==> Setting up Naukri Job Bot..."

# Create virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Create .env from template if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "  ✅ Created .env — fill in your credentials:"
    echo "     NAUKRI_EMAIL, NAUKRI_PASSWORD, ANTHROPIC_API_KEY (or OPENAI_API_KEY)"
    echo ""
fi

# Create dirs
mkdir -p data logs screenshots

echo "==> Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Naukri login + LLM API key"
echo "  2. Edit resume/resume.json with your profile"
echo "  3. Run: source .venv/bin/activate && python -m src.main run --once"
echo "  4. For live dashboard: python -m src.main dashboard"
