"""Notion API integration functions."""
from config import notion


def extract_text_from_block(block):
    """Extract text content from a Notion block."""
    text_content = []
    
    if block.get("type") == "paragraph":
        for text in block["paragraph"]["rich_text"]:
            text_content.append(text["plain_text"])
    elif block.get("type") == "heading_1":
        for text in block["heading_1"]["rich_text"]:
            text_content.append(f"# {text['plain_text']}")
    elif block.get("type") == "heading_2":
        for text in block["heading_2"]["rich_text"]:
            text_content.append(f"## {text['plain_text']}")
    elif block.get("type") == "heading_3":
        for text in block["heading_3"]["rich_text"]:
            text_content.append(f"### {text['plain_text']}")
    elif block.get("type") == "bulleted_list_item":
        for text in block["bulleted_list_item"]["rich_text"]:
            text_content.append(f"- {text['plain_text']}")
    elif block.get("type") == "numbered_list_item":
        for text in block["numbered_list_item"]["rich_text"]:
            text_content.append(f"1. {text['plain_text']}")
    elif block.get("type") == "code":
        for text in block["code"]["rich_text"]:
            text_content.append(f"```\n{text['plain_text']}\n```")
    
    return "\n".join(text_content)


def fetch_notion_page_content(page_id):
    """Fetch all content from a Notion page."""
    content_parts = []
    
    # Get page title
    page = notion.pages.retrieve(page_id)
    if page.get("properties"):
        # Try to get title from properties
        for prop_name, prop_value in page["properties"].items():
            if prop_value.get("type") == "title":
                title_parts = prop_value.get("title", [])
                if title_parts:
                    title = "".join([t["plain_text"] for t in title_parts])
                    content_parts.append(f"# {title}\n")
    
    # Get all blocks from the page
    blocks = notion.blocks.children.list(page_id)
    
    for block in blocks["results"]:
        text = extract_text_from_block(block)
        if text:
            content_parts.append(text)
        
        # Handle nested blocks (e.g., children of blocks)
        if block.get("has_children"):
            child_blocks = notion.blocks.children.list(block["id"])
            for child_block in child_blocks["results"]:
                child_text = extract_text_from_block(child_block)
                if child_text:
                    content_parts.append(child_text)
    
    return "\n\n".join(content_parts)


def fetch_multiple_notion_pages(page_ids):
    """Fetch content from multiple Notion pages."""
    all_content = []
    
    for page_id in page_ids:
        page_id = page_id.strip()  # Remove any whitespace
        if page_id:
            content = fetch_notion_page_content(page_id)
            if content:
                all_content.append(content)
    
    return "\n\n---\n\n".join(all_content)


def fetch_notion_database_pages(database_id, max_pages=10):
    """Fetch pages from a Notion database."""
    all_content = []
    
    results = notion.databases.query(database_id)
    pages = results.get("results", [])[:max_pages]
    
    for page in pages:
        page_id = page["id"]
        content = fetch_notion_page_content(page_id)
        if content:
            all_content.append(content)
    
    return "\n\n---\n\n".join(all_content)
