#!/bin/bash

# Startup script for pasta.py Mastodon Post Generator
# This script runs automatically when the VM boots

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Logging setup
LOG_FILE="/var/log/sundai/startup.log"
mkdir -p /var/log/sundai
chmod 755 /var/log/sundai

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE" >&2
}

log "=========================================="
log "Setting up pasta.py application"
log "=========================================="

# Update system packages
log "Updating system packages..."
if ! apt-get update -y >> "$LOG_FILE" 2>&1; then
    log_error "Failed to update package lists"
    exit 1
fi

log "Upgrading system packages..."
if ! DEBIAN_FRONTEND=noninteractive apt-get upgrade -y >> "$LOG_FILE" 2>&1; then
    log_error "Failed to upgrade packages"
    exit 1
fi

# Install required system packages
log "Installing system dependencies..."
if ! DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    build-essential \
    python3-dev >> "$LOG_FILE" 2>&1; then
    log_error "Failed to install system dependencies"
    exit 1
fi

log "System dependencies installed successfully"

# Create application directory
APP_DIR="/opt/sundai"
log "Creating application directory at $APP_DIR..."
mkdir -p "$APP_DIR"
cd "$APP_DIR" || exit 1

# Note: The application code should be uploaded to this directory
# For now, we'll set up the environment structure
log "Setting up application structure..."

# Create virtual environment
log "Creating Python virtual environment..."
if ! python3 -m venv venv >> "$LOG_FILE" 2>&1; then
    log_error "Failed to create Python virtual environment"
    exit 1
fi

# Activate virtual environment and upgrade pip
log "Activating virtual environment and upgrading pip..."
source venv/bin/activate
if ! pip install --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1; then
    log_error "Failed to upgrade pip"
    exit 1
fi
log "pip upgraded successfully"

# Create a placeholder requirements.txt if it doesn't exist
# (This will be replaced when code is uploaded)
if [ ! -f requirements.txt ]; then
    cat > requirements.txt << 'EOF'
openai>=1.0.0
notion-client>=2.2.0
Mastodon.py>=1.8.0
replicate>=0.25.0
requests>=2.31.0
python-telegram-bot>=20.0
python-dotenv>=1.0.0
EOF
fi

# Install Python dependencies
log "Installing Python dependencies..."
if [ -f requirements.txt ]; then
    log "Found requirements.txt, installing dependencies..."
    if ! pip install -r requirements.txt >> "$LOG_FILE" 2>&1; then
        log_error "Failed to install Python dependencies from requirements.txt"
        exit 1
    fi
    log "Python dependencies installed successfully"
else
    log "Warning: requirements.txt not found, skipping dependency installation"
    log "Dependencies will be installed when application code is uploaded"
fi

# Create .env placeholder with instructions
if [ ! -f .env ]; then
    log "Creating .env placeholder file..."
    cat > .env << 'EOF'
# Environment variables for pasta.py
# Replace these with your actual API keys and configuration

# Notion API Configuration
NOTION_API_KEY=your-notion-api-key-here

# OpenRouter API Configuration
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Notion Content Source (use either DATABASE_ID or PAGE_ID)
NOTION_DATABASE_ID=your-database-id-here
# OR
NOTION_PAGE_ID=your-page-id-here

# Mastodon Configuration
MASTODON_INSTANCE_URL=https://your-instance.com
MASTODON_ACCESS_TOKEN=your-mastodon-access-token-here

# Replicate Configuration
REPLICATE_API_TOKEN=your-replicate-api-token-here
REPLICATE_MODEL=your-model-name:version

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here
TELEGRAM_CHAT_ID=your-telegram-chat-id-here
EOF
    log "Created .env placeholder file. Please update it with your actual credentials."
fi

# Set proper permissions
log "Setting directory permissions..."
chown -R root:root "$APP_DIR"
chmod -R 755 "$APP_DIR"

log "=========================================="
log "Setup complete!"
log "=========================================="
log "Application directory: $APP_DIR"
log ""
log "Next steps:"
log "1. Upload your application code to $APP_DIR"
log "2. Update $APP_DIR/.env with your actual API keys"
log "3. Install the systemd service (if using): sudo cp deploy/pasta.service /etc/systemd/system/"
log "4. Start the service: sudo systemctl start pasta"
log ""
log "To manually run the application:"
log "  cd $APP_DIR"
log "  source venv/bin/activate"
log "  python3 pasta.py"
log "=========================================="

# Log completion
log "Startup script completed successfully"
