"""LLM/text generation functions."""
import re
import json
from config import llm_client
from utils import truncate_post_to_limit


def generate_mastodon_post(notion_content):
    """Generate a Mastodon post based on Notion content."""
    
    system_prompt = """You are a social media content creator. Based on the provided documents, create an engaging Mastodon post.
    
Guidelines:
- Create a single, engaging Mastodon post (MUST be 500 characters or less - this is a hard limit)
- Make it shareable and engaging
- Use hashtags strategically (2-5 relevant hashtags)
- Maintain the key messages from the source material
- Write in a conversational, authentic tone
- Do NOT include any numbering or formatting like "1.", "2.", etc. - just write the post directly
- IMPORTANT: Keep your response under 500 characters total"""

    user_message = f"""Based on the following documents from Notion, create a Mastodon post (max 500 characters):

{notion_content}

Generate the post now (just the post text, no numbering or extra formatting, under 500 characters):"""

    response = llm_client.chat.completions.create(
        model="nvidia/nemotron-3-nano-30b-a3b:free",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    post_content = response.choices[0].message.content.strip()
    
    # Clean up any numbering or formatting the LLM might have added
    # Remove leading numbers like "1.", "2.", etc.
    post_content = re.sub(r'^\d+[\.\)]\s*', '', post_content, flags=re.MULTILINE)
    # Remove "Post:" or similar prefixes
    post_content = re.sub(r'^(Post|Mastodon Post|Here\'s the post):\s*', '', post_content, flags=re.IGNORECASE)
    post_content = post_content.strip()
    
    # Enforce 500 character limit
    if len(post_content) > 500:
        post_content = truncate_post_to_limit(post_content, max_length=500)
        print(f"⚠️  Post exceeded 500 characters and was truncated to {len(post_content)} characters")
    
    return post_content


def generate_replies_to_posts(posts, business_context=""):
    """Generate replies to multiple posts using structured outputs."""
    
    # Format posts for the LLM
    posts_text = ""
    for i, post in enumerate(posts, 1):
        posts_text += f"""
Post {i}:
Author: @{post['author']} ({post.get('author_display', '')})
Content: {post['content']}
URL: {post['url']}
---
"""
    
    system_prompt = """You are a helpful assistant that crafts engaging, authentic replies to social media posts.
Generate thoughtful replies that:
- Are concise and conversational (under 500 characters)
- Add value to the conversation
- Are authentic and personable
- Reference specific parts of the original post when relevant
- Include relevant hashtags if appropriate (1-3 max)

Return your replies as a JSON object with this exact structure:
{
  "replies": [
    {
      "post_number": 1,
      "reply_text": "Your reply text here"
    },
    {
      "post_number": 2,
      "reply_text": "Your reply text here"
    }
  ]
}

Make sure the JSON is valid and properly formatted."""
    
    context_note = f"\n\nBusiness Context: {business_context}\n" if business_context else ""
    
    user_message = f"""Here are posts I want to reply to:{context_note}

{posts_text}

Generate appropriate replies for all {len(posts)} posts. Return ONLY valid JSON with the structure specified above."""

    try:
        # Try with JSON mode first
        try:
            response = llm_client.chat.completions.create(
                model="nvidia/nemotron-3-nano-30b-a3b:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"}  # Structured output
            )
        except Exception as e:
            # If JSON mode not supported, try without it
            print(f"⚠️  JSON mode not supported, trying without...")
            response = llm_client.chat.completions.create(
                model="nvidia/nemotron-3-nano-30b-a3b:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
            )
        
        content = response.choices[0].message.content.strip()
        
        # Try to extract JSON from the response if it's wrapped in text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        
        reply_data = json.loads(content)
        return reply_data.get('replies', [])
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON response: {e}")
        print(f"Raw response: {response.choices[0].message.content[:500]}")
        return []
    except Exception as e:
        print(f"❌ Error generating replies: {e}")
        return []


def generate_image_prompt_from_post(post_text):
    """Generate an image generation prompt based on the post text."""
    system_prompt = """You are a prompt engineer for image generation. Based on a social media post, create a concise, descriptive prompt for generating a relevant image.
    
Guidelines:
- Keep the prompt under 100 words
- Focus on visual elements, mood, and setting
- Make it suitable for image generation
- Include the trigger word "jace" in the prompt
- Be specific about composition, lighting, and style
- Return ONLY the prompt, no explanation or extra text"""

    user_message = f"""Create an image generation prompt for this post:

{post_text}

Image prompt:"""

    try:
        response = llm_client.chat.completions.create(
            model="nvidia/nemotron-3-nano-30b-a3b:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        
        prompt = response.choices[0].message.content.strip()
        # Ensure "jace" is in the prompt (the trigger word)
        if "jace" not in prompt.lower():
            prompt = f"jace, {prompt}"
        
        return prompt
    except Exception as e:
        print(f"⚠️  Error generating image prompt: {e}")
        # Fallback: use post text with trigger word
        return f"jace, {post_text[:200]}"
