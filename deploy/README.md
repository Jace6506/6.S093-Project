# GCP VM Deployment Guide

This guide explains how to deploy the pasta.py Mastodon Post Generator application to a Google Cloud Platform VM instance.

## Prerequisites

1. **Google Cloud Account**: You need a GCP account with billing enabled
2. **gcloud CLI**: Install the Google Cloud SDK
   ```bash
   # macOS
   brew install google-cloud-sdk
   
   # Or download from: https://cloud.google.com/sdk/docs/install
   ```
3. **Authentication**: Authenticate with Google Cloud
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
4. **Project Access**: Ensure you have access to the `jace-sundai` project

## Quick Start

1. **Make deployment scripts executable**:
   ```bash
   chmod +x deploy/deploy-vm.sh
   chmod +x deploy/startup-script.sh
   ```

2. **Deploy the VM**:
   ```bash
   cd /path/to/Sundai
   ./deploy/deploy-vm.sh
   ```

3. **Wait for VM initialization** (2-3 minutes)

4. **Upload application code**:
   ```bash
   gcloud compute scp --recurse . jacevmslop:/opt/sundai --zone=us-east1-b
   ```

5. **Upload your .env file**:
   ```bash
   gcloud compute scp .env jacevmslop:/opt/sundai/.env --zone=us-east1-b
   ```

6. **SSH into the VM**:
   ```bash
   gcloud compute ssh jacevmslop --zone=us-east1-b
   ```

7. **Start the application** (choose one method):

   **Option A: Run manually**:
   ```bash
   cd /opt/sundai
   source venv/bin/activate
   python3 pasta.py
   ```

   **Option B: Install as systemd service** (recommended for production):
   ```bash
   cd /opt/sundai
   sudo cp deploy/pasta.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable pasta
   sudo systemctl start pasta
   
   # Check status
   sudo systemctl status pasta
   
   # View logs
   sudo journalctl -u pasta -f
   ```

## VM Configuration

- **Project**: `jace-sundai`
- **VM Name**: `jacevmslop`
- **Machine Type**: `e2-standard-2` (2 vCPU, 8 GB RAM)
- **Zone**: `us-east1-b`
- **OS**: Ubuntu 22.04 LTS
- **Boot Disk**: 20GB standard persistent disk

## Startup Script

The VM automatically runs `deploy/startup-script.sh` on first boot. This script:
- Updates system packages
- Installs Python 3, pip, git, and dependencies
- Creates a virtual environment at `/opt/sundai/venv`
- Installs Python packages from `requirements.txt`
- Sets up the application directory structure
- Creates a placeholder `.env` file

## Application Directory Structure

The application is installed at `/opt/sundai/`:
```
/opt/sundai/
├── venv/              # Python virtual environment
├── pasta.py           # Main application entry point
├── config.py          # Configuration module
├── modes.py           # Workflow modes
├── .env               # Environment variables (upload this)
├── requirements.txt   # Python dependencies
└── ...               # Other application files
```

## Managing the Application

### Check VM Status
```bash
gcloud compute instances describe jacevmslop --zone=us-east1-b
```

### View Startup Script Logs
```bash
gcloud compute ssh jacevmslop --zone=us-east1-b --command="sudo journalctl -u google-startup-scripts.service -n 100"
```

### Systemd Service Commands
```bash
# Start service
sudo systemctl start pasta

# Stop service
sudo systemctl stop pasta

# Restart service
sudo systemctl restart pasta

# Check status
sudo systemctl status pasta

# View logs
sudo journalctl -u pasta -f

# Disable auto-start on boot
sudo systemctl disable pasta

# Enable auto-start on boot
sudo systemctl enable pasta
```

### Manual Application Management
```bash
# SSH into VM
gcloud compute ssh jacevmslop --zone=us-east1-b

# Activate virtual environment
cd /opt/sundai
source venv/bin/activate

# Run application
python3 pasta.py
```

## Updating the Application

1. **Make changes locally**

2. **Upload updated files**:
   ```bash
   gcloud compute scp --recurse . jacevmslop:/opt/sundai --zone=us-east1-b
   ```

3. **SSH into VM and restart**:
   ```bash
   gcloud compute ssh jacevmslop --zone=us-east1-b
   cd /opt/sundai
   source venv/bin/activate
   
   # If using systemd
   sudo systemctl restart pasta
   
   # Or run manually
   python3 pasta.py
   ```

## Updating Dependencies

If `requirements.txt` changes:

1. **Upload new requirements.txt**:
   ```bash
   gcloud compute scp requirements.txt jacevmslop:/opt/sundai/requirements.txt --zone=us-east1-b
   ```

2. **SSH and reinstall**:
   ```bash
   gcloud compute ssh jacevmslop --zone=us-east1-b
   cd /opt/sundai
   source venv/bin/activate
   pip install -r requirements.txt
   ```

## Environment Variables

The `.env` file contains sensitive API keys. **Never commit this file to version control**.

Required environment variables:
- `NOTION_API_KEY`
- `OPENROUTER_API_KEY`
- `NOTION_DATABASE_ID` or `NOTION_PAGE_ID`
- `MASTODON_INSTANCE_URL`
- `MASTODON_ACCESS_TOKEN`
- `REPLICATE_API_TOKEN` (optional)
- `REPLICATE_MODEL` (optional)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Troubleshooting

### VM Won't Start
```bash
# Check VM status
gcloud compute instances describe jacevmslop --zone=us-east1-b

# Check startup script logs
gcloud compute ssh jacevmslop --zone=us-east1-b --command="cat /var/log/sundai/startup.log"
```

### Application Errors
```bash
# Check systemd logs
sudo journalctl -u pasta -n 100

# Check Python errors
cd /opt/sundai
source venv/bin/activate
python3 pasta.py
```

### Network Issues
The VM has internet access by default. If you need to allow specific ports:
```bash
gcloud compute firewall-rules create allow-pasta \
    --allow tcp:PORT_NUMBER \
    --source-ranges 0.0.0.0/0 \
    --description "Allow pasta.py traffic"
```

### Disk Space
Check disk usage:
```bash
gcloud compute ssh jacevmslop --zone=us-east1-b --command="df -h"
```

## Cost Management

- **Estimated monthly cost**: ~$30-50 for e2-standard-2 instance (varies by usage)
- **Stop VM when not in use**:
  ```bash
  gcloud compute instances stop jacevmslop --zone=us-east1-b
  ```
- **Start stopped VM**:
  ```bash
  gcloud compute instances start jacevmslop --zone=us-east1-b
  ```

## Security Considerations

1. **Keep .env file secure**: Never commit it to version control
2. **Use Secret Manager**: For production, consider using Google Cloud Secret Manager instead of .env files
3. **Firewall rules**: Only open necessary ports
4. **Service account**: The VM uses the default Compute Engine service account with minimal permissions
5. **SSH keys**: Use gcloud's built-in SSH key management

## Cleanup

To delete the VM and associated resources:
```bash
gcloud compute instances delete jacevmslop --zone=us-east1-b
```

## Support

For issues or questions:
1. Check the startup script logs: `/var/log/sundai/startup.log`
2. Check systemd logs: `sudo journalctl -u pasta`
3. Verify all environment variables are set correctly in `.env`
4. Ensure all API keys are valid and have proper permissions
