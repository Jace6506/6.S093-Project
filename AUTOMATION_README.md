# Automation Service - Parts 4 & 5

This document explains how to use the automation listeners for auto-posting and auto-replying.

## Overview

The automation service implements:
- **Part 4**: Auto-create posts when Notion pages are updated
- **Part 5**: Auto-reply to Mastodon comments/mentions

## Running the Automation Service

### Option 1: Standalone Service

Run the automation service as a separate process:

```bash
python automation_service.py
```

This will start both listeners:
- Notion page update checker (checks every 5 minutes by default)
- Mastodon notifications checker (checks every 1 minute by default)

### Option 2: Via API

The automation can be controlled via API endpoints:

**Start automation:**
```bash
curl -X POST http://localhost:8000/api/automation/start
```

**Stop automation:**
```bash
curl -X POST http://localhost:8000/api/automation/stop
```

**Check status:**
```bash
curl http://localhost:8000/api/automation/status
```

### Option 3: Auto-start with API

Set environment variable to auto-start listeners when API starts:

```bash
export AUTO_START_LISTENERS=true
python api.py
```

## Configuration

Add these to your `.env` file:

```bash
# Notion check interval (seconds) - default: 300 (5 minutes)
NOTION_CHECK_INTERVAL=300

# Mastodon check interval (seconds) - default: 60 (1 minute)
MASTODON_CHECK_INTERVAL=60

# Auto-start listeners when API starts
AUTO_START_LISTENERS=false
```

## How It Works

### Part 4: Auto-Create Posts

1. **Polls Notion** for page updates (checks `last_edited_time`)
2. **Detects changes** by comparing timestamps
3. **Re-embeds content** if the page was updated
4. **Uses RAG** to retrieve relevant context
5. **Generates post** using LLM with RAG context
6. **Optionally generates image** (if Replicate is configured)
7. **Posts to Mastodon** automatically
8. **Saves to database** with status "published"

### Part 5: Auto-Reply to Comments

1. **Polls Mastodon** for new notifications
2. **Filters for mentions/replies** (ignores other notification types)
3. **Extracts context** from the original post
4. **Optionally uses Notion content** as business context
5. **Generates reply** using LLM
6. **Posts reply** automatically
7. **Tracks processed notifications** to avoid duplicates

## Notes

- The service runs continuously until stopped (Ctrl+C or API stop)
- Notifications are tracked to prevent duplicate replies
- Posts are saved to the database for retrieval
- The service gracefully handles errors and continues running

## Testing

To test the automation:

1. **Test Part 4**: Update a Notion page and wait for the check interval
2. **Test Part 5**: Mention your Mastodon account in a post and wait for the check interval

## Troubleshooting

- **No posts created**: Check that Notion pages are being updated and that RAG embeddings exist
- **No replies sent**: Check that Mastodon notifications are being received
- **Service stops**: Check logs for errors - the service will retry after errors
