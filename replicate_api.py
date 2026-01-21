"""Replicate API integration for image generation."""
import os
import requests
from config import replicate_client, REPLICATE_MODEL


def generate_image_with_replicate(prompt):
    """Generate an image using Replicate."""
    if not replicate_client:
        print("⚠️  Replicate API not configured.")
        return None
    
    if not REPLICATE_MODEL:
        print("⚠️  REPLICATE_MODEL not set. Please set it in your .env file")
        print("   Example: REPLICATE_MODEL=username/model-name")
        print("   Or: REPLICATE_MODEL=username/model-name:version-id")
        return None
    
    try:
        print(f"   Generating image with prompt: {prompt[:100]}...")
        print("   This may take a minute...")
        print(f"   Using model: {REPLICATE_MODEL}")
        
        # Try different model formats
        model_to_use = REPLICATE_MODEL
        
        # If model has a colon, try it as-is first
        if ':' in REPLICATE_MODEL:
            try:
                output = replicate_client.run(
                    model_to_use,
                    input={"prompt": prompt}
                )
            except Exception as e:
                # If version fails, try without version (use latest)
                if "version" in str(e).lower() or "422" in str(e):
                    print(f"   ⚠️  Version issue, trying model without version...")
                    model_to_use = REPLICATE_MODEL.split(':')[0]
                    output = replicate_client.run(
                        model_to_use,
                        input={"prompt": prompt}
                    )
                else:
                    raise
        
        # If no colon, use as-is
        else:
            output = replicate_client.run(
                model_to_use,
                input={"prompt": prompt}
            )
        
        # Replicate returns a URL or list of URLs
        if isinstance(output, list):
            image_url = output[0] if output else None
        else:
            image_url = output
        
        if image_url:
            print(f"   ✅ Image generated successfully!")
            return image_url
        else:
            print("   ⚠️  No image URL returned")
            return None
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error generating image: {error_msg}")
        
        # Provide helpful troubleshooting
        if "422" in error_msg or "version" in error_msg.lower() or "permission" in error_msg.lower():
            print("\n💡 Troubleshooting tips:")
            print("   1. Check your REPLICATE_MODEL format:")
            print("      - Try: username/model-name (without version)")
            print("      - Or: username/model-name:version-id")
            print(f"   2. Current model: {REPLICATE_MODEL}")
            print("   3. Make sure the model exists and you have access to it")
            print("   4. Check your Replicate dashboard: https://replicate.com/models")
            print("   5. For finetuned models, use: your-username/model-name")
        
        return None


def download_image(image_url, save_path):
    """Download an image from a URL to a local file."""
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return save_path
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        return None
