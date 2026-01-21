"""Utility functions."""
import os
import tempfile
import subprocess


def truncate_post_to_limit(post_content, max_length=500):
    """Truncate post content to fit within character limit, preserving words."""
    if len(post_content) <= max_length:
        return post_content
    
    # Truncate to max_length, but try to end at a word boundary
    truncated = post_content[:max_length]
    # Find the last space before the limit
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.9:  # Only use word boundary if it's not too short
        truncated = truncated[:last_space]
    
    # Add ellipsis if truncated
    if len(truncated) < len(post_content):
        truncated = truncated.rstrip() + "..."
    
    return truncated


def edit_post_content(post_content):
    """Allow user to edit the post content using their default editor."""
    # Create a temporary file with the current post content
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tmp_file:
        tmp_file.write(post_content)
        tmp_file_path = tmp_file.name
    
    # Determine which editor to use
    editor = os.environ.get('EDITOR', 'nano')  # Default to nano if $EDITOR not set
    
    # On macOS, try to use a GUI editor if available, otherwise use nano
    if os.name == 'posix' and 'EDITOR' not in os.environ:
        # Try common editors in order of preference
        for possible_editor in ['nano', 'vim', 'vi', 'code', 'subl']:
            try:
                subprocess.run(['which', possible_editor], 
                             check=True, capture_output=True)
                editor = possible_editor
                break
            except subprocess.CalledProcessError:
                continue
    
    print(f"\nOpening editor ({editor})...")
    print("Make your edits, save, and close the editor when done.")
    print("-" * 50)
    
    # Open the file in the editor
    try:
        if editor in ['code', 'subl']:
            # For GUI editors, run in background
            subprocess.run([editor, tmp_file_path], check=True)
        else:
            # For terminal editors, run in foreground
            subprocess.run([editor, tmp_file_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error opening editor: {e}")
        print("Falling back to simple text input...")
        # Fallback: just ask for new content
        print("\nEnter your edited post (press Enter twice when done, max 500 characters):")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        edited_content = "\n".join(lines[:-1])  # Remove the last empty line
        edited_content = edited_content.strip()
        os.unlink(tmp_file_path)
        
        # Validate and truncate if necessary
        if len(edited_content) > 500:
            print(f"\n⚠️  Warning: Edited post is {len(edited_content)} characters (exceeds 500 limit)")
            edited_content = truncate_post_to_limit(edited_content, max_length=500)
            print(f"   Truncated to {len(edited_content)} characters")
        
        return edited_content
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Using simple text input...")
        print("\nEnter your edited post (press Enter twice when done, max 500 characters):")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        edited_content = "\n".join(lines[:-1])
        edited_content = edited_content.strip()
        os.unlink(tmp_file_path)
        
        # Validate and truncate if necessary
        if len(edited_content) > 500:
            print(f"\n⚠️  Warning: Edited post is {len(edited_content)} characters (exceeds 500 limit)")
            edited_content = truncate_post_to_limit(edited_content, max_length=500)
            print(f"   Truncated to {len(edited_content)} characters")
        
        return edited_content
    
    # Read the edited content
    try:
        with open(tmp_file_path, 'r') as f:
            edited_content = f.read().strip()
        os.unlink(tmp_file_path)  # Clean up temp file
        
        # Validate and truncate if necessary
        if len(edited_content) > 500:
            print(f"\n⚠️  Warning: Edited post is {len(edited_content)} characters (exceeds 500 limit)")
            edited_content = truncate_post_to_limit(edited_content, max_length=500)
            print(f"   Truncated to {len(edited_content)} characters")
        
        return edited_content
    except Exception as e:
        print(f"Error reading edited file: {e}")
        return post_content  # Return original if something went wrong
