# Mastodon Post Generator

Automate your Mastodon social media presence by generating posts from Notion content and crafting replies to existing posts.

## Features

- 🚀 **Generate New Posts**: Create engaging Mastodon posts from your Notion documents
- 💬 **Craft Replies**: Automatically generate thoughtful replies to existing posts by keyword
- ✏️ **Edit Before Posting**: Review and edit generated content before publishing
- 🔍 **Smart Search**: Find relevant posts to engage with based on keywords
- 📝 **Notion Integration**: Pull content directly from Notion pages or databases

## Setup

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

Add your credentials:

```
# Notion API Configuration
NOTION_API_KEY=your-notion-api-key-here

# OpenRouter API Configuration
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Notion Content Source (use either DATABASE_ID or PAGE_ID)
NOTION_DATABASE_ID=your-database-id-here
# OR
NOTION_PAGE_ID=your-page-id-here,another-page-id-here

# Mastodon Configuration
MASTODON_INSTANCE_URL=https://your-instance.com
MASTODON_ACCESS_TOKEN=your-mastodon-access-token-here
```

### 3. Get Your API Keys

- **Notion**: Go to https://www.notion.so/my-integrations → Create new integration → Copy API key
- **OpenRouter**: Get your API key from https://openrouter.ai/
- **Mastodon**: Go to Settings → Development → New application → Copy access token

### 4. Share Notion Pages

Make sure to share your Notion pages/databases with your integration:
1. Open the Notion page/database
2. Click the "..." menu (top right)
3. Click "Add connections"
4. Select your integration

## Usage

Run the script:

```bash
source venv/bin/activate
python3 pasta.py
```

Choose your mode:
1. **Create a new post** from Notion content
2. **Craft replies** to existing posts

## Requirements

- Python 3.8+
- Notion account with API access
- OpenRouter API key
- Mastodon account with API access

## License

MIT
