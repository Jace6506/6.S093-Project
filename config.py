"""Configuration and client initialization."""
import os
from openai import OpenAI
from notion_client import Client
from mastodon import Mastodon
import replicate

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip loading .env file

# Initialize Notion client
notion = Client(auth=os.environ.get("NOTION_API_KEY"))

# Initialize OpenAI client (OpenRouter)
llm_client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)

# Initialize Mastodon client
MASTODON_INSTANCE_URL = os.environ.get("MASTODON_INSTANCE_URL", "").strip()
MASTODON_ACCESS_TOKEN = os.environ.get("MASTODON_ACCESS_TOKEN", "").strip()

# Format instance URL properly (remove trailing slash, ensure https)
if MASTODON_INSTANCE_URL:
    MASTODON_INSTANCE_URL = MASTODON_INSTANCE_URL.rstrip('/')
    if not MASTODON_INSTANCE_URL.startswith('http'):
        MASTODON_INSTANCE_URL = f"https://{MASTODON_INSTANCE_URL}"

if MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN:
    try:
        mastodon = Mastodon(
            access_token=MASTODON_ACCESS_TOKEN,
            api_base_url=MASTODON_INSTANCE_URL
        )
        # Test the connection by verifying credentials
        mastodon.account_verify_credentials()
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize Mastodon client: {e}")
        print(f"   Instance URL: {MASTODON_INSTANCE_URL}")
        print("   Please check your MASTODON_INSTANCE_URL and MASTODON_ACCESS_TOKEN")
        mastodon = None
else:
    mastodon = None

# Initialize Replicate client
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "").strip()
REPLICATE_MODEL = os.environ.get("REPLICATE_MODEL", "").strip()  # e.g., "username/model-name:version"

if REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
    replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
else:
    replicate_client = None
