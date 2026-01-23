#!/bin/bash

# Deploy GCP VM for pasta.py application
# This script creates a VM instance with the specified configuration
#
# Usage:
#   ./deploy-vm.sh [ZONE]
#   or
#   ZONE=us-west1-a ./deploy-vm.sh

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
PROJECT_ID="jace-sundai"
VM_NAME="jacevmslop"
MACHINE_TYPE="e2-standard-2"
ZONE="${1:-${ZONE:-us-east1-b}}"  # Allow zone from arg or env var, default to us-east1-b
BOOT_DISK_SIZE="20GB"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"
STARTUP_SCRIPT_PATH="$(dirname "$0")/startup-script.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
error() {
    echo -e "${RED}Error:${NC} $1" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}Warning:${NC} $1" >&2
}

info() {
    echo -e "${BLUE}Info:${NC} $1"
}

success() {
    echo -e "${GREEN}Success:${NC} $1"
}

echo "=========================================="
echo "Deploying GCP VM for pasta.py"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "VM Name: $VM_NAME"
echo "Machine Type: $MACHINE_TYPE"
echo "Zone: $ZONE"
echo "=========================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    error "gcloud CLI is not installed.\nPlease install it from: https://cloud.google.com/sdk/docs/install"
fi

# Check if user is authenticated
info "Checking gcloud authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    error "No active gcloud authentication found.\nPlease run: gcloud auth login"
fi

ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1)
info "Authenticated as: $ACTIVE_ACCOUNT"

# Set the project
info "Setting GCP project to $PROJECT_ID..."
if ! gcloud config set project "$PROJECT_ID" 2>/dev/null; then
    error "Failed to set project. Please verify you have access to project '$PROJECT_ID'"
fi

# Verify project access
info "Verifying project access..."
if ! gcloud projects describe "$PROJECT_ID" &>/dev/null; then
    error "Cannot access project '$PROJECT_ID'. Please verify:\n  1. The project ID is correct\n  2. You have the necessary permissions\n  3. Billing is enabled for this project"
fi

# Verify zone exists
info "Verifying zone $ZONE..."
if ! gcloud compute zones describe "$ZONE" --project="$PROJECT_ID" &>/dev/null; then
    error "Zone '$ZONE' not found or not available in project '$PROJECT_ID'.\nPlease verify the zone name or try a different zone."
fi

# Check if startup script exists
if [ ! -f "$STARTUP_SCRIPT_PATH" ]; then
    error "Startup script not found at $STARTUP_SCRIPT_PATH"
fi

# Verify startup script is executable (or make it so)
if [ ! -x "$STARTUP_SCRIPT_PATH" ]; then
    warning "Startup script is not executable, making it executable..."
    chmod +x "$STARTUP_SCRIPT_PATH"
fi

# Check if VM already exists
info "Checking if VM instance already exists..."
if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" &>/dev/null; then
    warning "VM instance '$VM_NAME' already exists in zone $ZONE"
    read -p "Do you want to delete and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Deleting existing VM..."
        if ! gcloud compute instances delete "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --quiet; then
            error "Failed to delete existing VM instance"
        fi
        info "Waiting for VM deletion to complete..."
        sleep 5
    else
        error "Aborting. Please delete the existing VM manually or choose a different name."
    fi
fi

# Get default service account
info "Retrieving default service account..."
SERVICE_ACCOUNT=$(gcloud iam service-accounts list \
    --format="value(email)" \
    --filter="displayName:Compute Engine default service account" \
    --limit=1 \
    --project="$PROJECT_ID" 2>/dev/null)

if [ -z "$SERVICE_ACCOUNT" ]; then
    warning "Could not find default service account, using project number format..."
    PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
    SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi

info "Using service account: $SERVICE_ACCOUNT"

# Create the VM instance
info "Creating VM instance (this may take a few minutes)..."
if ! gcloud compute instances create "$VM_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --network-interface=network-tier=PREMIUM,stack-type=IPV4_ONLY \
    --maintenance-policy=MIGRATE \
    --provisioning-model=STANDARD \
    --service-account="$SERVICE_ACCOUNT" \
    --scopes=https://www.googleapis.com/auth/cloud-platform \
    --tags=http-server,https-server \
    --create-disk=auto-delete=yes,boot=yes,device-name="$VM_NAME",image=projects/$IMAGE_PROJECT/global/images/family/$IMAGE_FAMILY,mode=rw,size=$BOOT_DISK_SIZE,type=projects/$PROJECT_ID/zones/$ZONE/diskTypes/pd-standard \
    --no-shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --labels=app=pasta,environment=production \
    --reservation-affinity=any \
    --metadata-from-file=startup-script="$STARTUP_SCRIPT_PATH"; then
    error "Failed to create VM instance"
fi

# Get VM external IP
info "Retrieving VM external IP address..."
EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || echo "Not available yet")

echo ""
echo "=========================================="
success "VM created successfully!"
echo "=========================================="
echo "VM Name: $VM_NAME"
echo "Zone: $ZONE"
echo "External IP: ${EXTERNAL_IP:-Not assigned yet}"
echo ""
info "Next steps:"
echo ""
echo "1. Wait for the VM to finish initializing (2-3 minutes)"
echo "   Check startup script logs:"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE --command=\"sudo journalctl -u google-startup-scripts.service -n 100\""
echo ""
echo "2. Upload your application code:"
echo "   gcloud compute scp --recurse . $VM_NAME:/opt/sundai --zone=$ZONE"
echo ""
echo "3. Upload your .env file:"
echo "   gcloud compute scp .env $VM_NAME:/opt/sundai/.env --zone=$ZONE"
echo ""
echo "4. SSH into the VM:"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE"
echo ""
echo "5. Start the application (choose one method):"
echo ""
echo "   Option A - Run manually:"
echo "   cd /opt/sundai"
echo "   source venv/bin/activate"
echo "   python3 pasta.py"
echo ""
echo "   Option B - Install as systemd service (recommended):"
echo "   sudo cp /opt/sundai/deploy/pasta.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable pasta"
echo "   sudo systemctl start pasta"
echo "   sudo systemctl status pasta"
echo ""
echo "=========================================="
