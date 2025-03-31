#!/usr/bin/env python3
import os
import datetime
import zipfile
from pathspec import PathSpec

def load_gitignore(gitignore_path):
    """Load non-empty, non-comment lines from a .gitignore file."""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            lines = [line.rstrip() for line in f if line.strip() and not line.lstrip().startswith("#")]
        return lines
    return []

def should_ignore(path, spec):
    """
    Check if a given path (relative, using OS separators) should be ignored
    by normalizing to posix-style (forward slashes) for matching.
    """
    norm_path = path.replace(os.sep, '/')
    return spec.match_file(norm_path)

def main():
    # Get current working directory and its base name.
    cwd = os.getcwd()
    base_dir = os.path.basename(cwd)
    
    # Build output zip filename: <base_dir>-yyyy-mm-dd-hh-mm-ss.zip
    date_time_str = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    zip_filename = f"{base_dir}-{date_time_str}.zip"
    
    # Place the zip file in the current directory.
    zip_filepath = os.path.join(cwd, zip_filename)
    
    # Load .gitignore patterns from the root of the current directory.
    gitignore_path = os.path.join(cwd, ".gitignore")
    gitignore_lines = load_gitignore(gitignore_path)
    spec = PathSpec.from_lines('gitwildmatch', gitignore_lines)
    
    # Create the zip file with compression.
    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(cwd):
            # Compute the path relative to the current directory.
            rel_root = os.path.relpath(root, cwd)
            if rel_root == '.':
                rel_root = ''
                
            # Filter out directories that should be ignored.
            dirs[:] = [d for d in dirs if not should_ignore(os.path.join(rel_root, d), spec)]
            
            for file in files:
                file_rel_path = os.path.join(rel_root, file)
                abs_path = os.path.join(root, file)
                
                # Skip files that match the .gitignore.
                if should_ignore(file_rel_path, spec):
                    continue
                
                # Skip the zip file itself if encountered.
                if os.path.abspath(abs_path) == os.path.abspath(zip_filepath):
                    continue
                
                # Create archive name so that the zip file contains a top-level folder named base_dir.
                arcname = os.path.join(base_dir, file_rel_path)
                zipf.write(abs_path, arcname)
    
    print(f"Archive created: {zip_filepath}")

if __name__ == "__main__":
    main()
