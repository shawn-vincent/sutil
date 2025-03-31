#!/usr/bin/env python3
# sutil/clip_files.py
# tags: #util #clipboard 
"""
clip_files.py - Aggregate file contents based on glob patterns and tags,
                supporting both inclusion and exclusion rules.

Usage:
    python clip_files.py "<patternOrTag1>" "<patternOrTag2>" ...

Examples:
    python clip_files.py "*.py" "*.md"
    python clip_files.py +frontend "*.json" -*.test.json -+experimental
"""

import sys
import os
import fnmatch
import re

try:
    import pyperclip
except ImportError:
    sys.exit("Error: pyperclip module is required. Install via pip install pyperclip")

try:
    import pathspec
except ImportError:
    sys.exit("Error: pathspec module is required. Install via pip install pathspec")


def print_usage():
    usage = (
        "Usage: python clip_files.py \"<patternOrTag1>\" \"<patternOrTag2>\" ...\n"
        "\n"
        "Inclusion Arguments:\n"
        "  Glob Patterns: e.g. \"*.js\", \"*.sh\". If no wildcard, the pattern is\n"
        "                 transformed (e.g., \"main.py\" becomes \"*/main.py\").\n"
        "  Tags:          Any argument starting with a plus sign (+) is a tag (e.g., +frontend)\n"
        "\n"
        "Exclusion Arguments:\n"
        "  Glob Exclusions:  Any argument starting with '-' is an exclusion glob\n"
        "                    (e.g., -*.js excludes files matching that glob).\n"
        "  Tag Exclusions:   An exclusion starting with '-+' is a tag exclusion\n"
        "                    (e.g., -+backend excludes files tagged with #backend).\n"
    )
    print(usage)


def load_ignore_spec():
    """
    Load .gitignore from the current directory (assumed to be the repo root)
    and convert its lines according to Git’s documented rules.

    Rules applied:
      - Blank lines and lines beginning with unescaped '#' are ignored.
      - A leading "!" indicates negation; it is stripped, processed, then re‑prepended.
      - A pattern starting with "/" is anchored to the .gitignore’s directory,
        so we remove the leading slash.
      - If the remaining pattern (ignoring a trailing slash) contains no slash,
        it is considered "bare" and we prepend "**/" so it matches at any level.
      - If the pattern ends with a slash, we append "**" (if not already present)
        so that all files under that directory are matched.
    """
    gitignore_path = os.path.join(os.getcwd(), '.gitignore')
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, 'r') as f:
                raw_lines = f.read().splitlines()
        except Exception as e:
            sys.exit(f"Error reading .gitignore: {e}")

        processed_patterns = []
        for line in raw_lines:
            # Remove leading/trailing whitespace
            line = line.rstrip()
            if not line:
                continue  # blank line
            # Lines beginning with '#' are comments (unless the '#' is escaped)
            if line.lstrip().startswith('#'):
                continue

            negated = False
            if line.startswith('!'):
                negated = True
                line = line[1:]  # remove the "!"
            # Determine if pattern is anchored.
            anchored = False
            if line.startswith('/'):
                anchored = True
                line = line[1:]  # remove the leading "/"

            # Determine if pattern is directory-only (ends with '/')
            directory_only = False
            if line.endswith('/'):
                directory_only = True

            # Remove trailing slash temporarily (for testing “bareness”)
            test_pattern = line[:-1] if directory_only else line

            # If the pattern is not anchored and has no other slash,
            # it’s a bare pattern and should match at any level.
            if not anchored and '/' not in test_pattern:
                line = '**/' + line

            # If the pattern was directory-only and does not already end with '**',
            # append '**' so that its contents are also matched.
            if directory_only and not line.endswith('/**'):
                line = line + '**'

            # Re-prepend "!" if negated.
            if negated:
                line = '!' + line

            processed_patterns.append(line)

        try:
            # Let PathSpec compile the patterns using Git's wildmatch rules.
            return pathspec.PathSpec.from_lines('gitwildmatch', processed_patterns)
        except Exception as e:
            print(f"Warning: Could not compile ignore spec: {e}", file=sys.stderr)
    return None


def parse_arguments(args):
    """
    Parse command-line arguments into inclusion and exclusion categories.
    Returns a dictionary containing:
      - inclusion_patterns: list of glob patterns (transformed if needed)
      - inclusion_tags: list of tags (without leading '+')
      - exclusion_patterns: list of exclusion glob patterns
      - exclusion_tags: list of exclusion tags (without leading '+')
      - unmatched_*: duplicates for tracking which arguments remain unmatched.
    """
    inclusion_patterns = []
    inclusion_tags = []
    exclusion_patterns = []
    exclusion_tags = []
    unmatched_inclusion_patterns = []
    unmatched_inclusion_tags = []
    unmatched_exclusion_patterns = []
    unmatched_exclusion_tags = []

    for arg in args:
        if arg.startswith('-'):
            # Exclusion argument
            if len(arg) > 1 and arg[1] == '+':
                tag = arg[2:]
                exclusion_tags.append(tag)
                unmatched_exclusion_tags.append(tag)
            else:
                pattern = arg[1:]
                exclusion_patterns.append(pattern)
                unmatched_exclusion_patterns.append(pattern)
        else:
            # Inclusion argument
            if arg.startswith('+'):
                tag = arg[1:]
                inclusion_tags.append(tag)
                unmatched_inclusion_tags.append(tag)
            else:
                # Transform non-wildcard patterns (e.g., "main.py" -> "*/main.py")
                if '*' not in arg:
                    arg = "*/" + arg
                inclusion_patterns.append(arg)
                unmatched_inclusion_patterns.append(arg)

    return {
        'inclusion_patterns': inclusion_patterns,
        'inclusion_tags': inclusion_tags,
        'exclusion_patterns': exclusion_patterns,
        'exclusion_tags': exclusion_tags,
        'unmatched_inclusion_patterns': unmatched_inclusion_patterns,
        'unmatched_inclusion_tags': unmatched_inclusion_tags,
        'unmatched_exclusion_patterns': unmatched_exclusion_patterns,
        'unmatched_exclusion_tags': unmatched_exclusion_tags,
    }


def file_matches_inclusion(file_path, arg_data):
    """
    Check if file_path matches any inclusion glob pattern or tag.
    Returns a tuple:
      (matched: bool, used_inclusion_pattern: str or None,
       used_inclusion_tag: str or None, lines: list or None)
    'lines' holds the first 10 lines if read for tag matching.
    """
    matched = False
    used_pattern = None
    used_tag = None
    lines = None

    # Check inclusion glob patterns.
    for pattern in arg_data['inclusion_patterns']:
        if fnmatch.fnmatch(file_path, pattern):
            matched = True
            used_pattern = pattern
            break

    # If not matched by pattern and inclusion tags exist, check file's first 10 lines.
    if not matched and arg_data['inclusion_tags']:
        try:
            with open(file_path, 'r', errors='replace') as f:
                lines = [f.readline() for _ in range(10)]
                content = "".join(lines)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}", file=sys.stderr)
            return (False, None, None, lines)

        for tag in arg_data['inclusion_tags']:
            # Search for "tags:" followed by any text and then the tag preceded by '#' with word boundary.
            if re.search(r"tags:.*#" + re.escape(tag) + r"\b", content):
                matched = True
                used_tag = tag
                break

    return (matched, used_pattern, used_tag, lines)


def file_matches_exclusion(file_path, arg_data, lines_cache):
    """
    Check if file_path should be excluded based on exclusion glob patterns or tags.
    Returns a tuple:
       (exclusion_glob: str or None, exclusion_tag: str or None)
    If a match is found, the file should be excluded.
    """
    # Check exclusion glob patterns.
    for pattern in arg_data['exclusion_patterns']:
        if fnmatch.fnmatch(file_path, pattern):
            return (pattern, None)

    # Check exclusion tags.
    if arg_data['exclusion_tags']:
        content = ""
        if lines_cache is None:
            try:
                with open(file_path, 'r', errors='replace') as f:
                    lines = [f.readline() for _ in range(10)]
                    content = "".join(lines)
            except Exception as e:
                print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        else:
            content = "".join(lines_cache)
        for tag in arg_data['exclusion_tags']:
            if re.search(r"tags:.*#" + re.escape(tag) + r"\b", content):
                return (None, tag)

    return (None, None)


def main():
    # Parse command-line arguments.
    args = sys.argv[1:]
    if not args:
        print_usage()
        sys.exit(1)

    arg_data = parse_arguments(args)

    # Load .gitignore rules (if available and if pathspec is installed).
    ignore_spec = load_ignore_spec()

    # Recursively traverse the filesystem starting at the current directory.
    candidate_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            file_path = os.path.join(root, file)
            # Normalize file path.
            if not (file_path.startswith('./') or file_path.startswith('/')):
                file_path = "./" + file_path
            # Apply ignore rules if available.
            if ignore_spec:
                rel_path = os.path.relpath(file_path, os.getcwd())
                if ignore_spec.match_file(rel_path):
                    continue
            candidate_files.append(file_path)

    if not candidate_files:
        print("No candidate files found in the filesystem.")
        sys.exit(0)

    final_files = []
    # Process each candidate file.
    for file in candidate_files:
        include_match, used_incl_pattern, used_incl_tag, lines_cache = file_matches_inclusion(file, arg_data)
        if not include_match:
            continue

        # Mark the inclusion argument as used.
        if used_incl_pattern and used_incl_pattern in arg_data['unmatched_inclusion_patterns']:
            arg_data['unmatched_inclusion_patterns'].remove(used_incl_pattern)
        if used_incl_tag and used_incl_tag in arg_data['unmatched_inclusion_tags']:
            arg_data['unmatched_inclusion_tags'].remove(used_incl_tag)

        # Check exclusion rules.
        ex_pattern, ex_tag = file_matches_exclusion(file, arg_data, lines_cache)
        if ex_pattern or ex_tag:
            if ex_pattern and ex_pattern in arg_data['unmatched_exclusion_patterns']:
                arg_data['unmatched_exclusion_patterns'].remove(ex_pattern)
            if ex_tag and ex_tag in arg_data['unmatched_exclusion_tags']:
                arg_data['unmatched_exclusion_tags'].remove(ex_tag)
            continue

        final_files.append(file)

    if not final_files:
        print("No files matched the given patterns/tags after applying exclusions.")
        sys.exit(0)

    # Build aggregated output from matched files.
    aggregated_output = ""
    file_count = 0
    for file in final_files:
        print(f"📄 Copying file: {file}")
        file_count += 1
        aggregated_output += f"===== {file} =====\n"
        try:
            with open(file, 'r', errors='replace') as f:
                aggregated_output += f.read() + "\n"
        except Exception as e:
            print(f"Error reading file {file}: {e}", file=sys.stderr)

    # Copy the aggregated output to the clipboard.
    try:
        pyperclip.copy(aggregated_output)
    except Exception as e:
        print(f"Error copying to clipboard: {e}", file=sys.stderr)

    char_count = len(aggregated_output)
    print(f"📄 Copied {file_count} files ({char_count} characters) to the clipboard.")

    # Warn about any unmatched arguments.
    if (arg_data['unmatched_inclusion_patterns'] or arg_data['unmatched_inclusion_tags'] or
        arg_data['unmatched_exclusion_patterns'] or arg_data['unmatched_exclusion_tags']):
        print("⚠️ Some arguments didn't match any files:")
        for pattern in arg_data['unmatched_inclusion_patterns']:
            print(f"⚠️ Unmatched inclusion pattern: {pattern}")
        for tag in arg_data['unmatched_inclusion_tags']:
            print(f"⚠️ Unmatched inclusion tag: +{tag}")
        for pattern in arg_data['unmatched_exclusion_patterns']:
            print(f"⚠️ Unmatched exclusion pattern: {pattern}")
        for tag in arg_data['unmatched_exclusion_tags']:
            print(f"⚠️ Unmatched exclusion tag: -+{tag}")


if __name__ == '__main__':
    main()



'''
===============================================================================
                              CLIP_FILES.PY
                        REQUIREMENTS DOCUMENT
===============================================================================
Project       : clip_files.py
Description   : Command-line utility to aggregate file contents based on
                glob patterns and tags, with inclusion and exclusion support.
Version       : 1.1
Date          : 2025-03-31
===============================================================================

1. OVERVIEW
-----------
clip_files.py is a Python 3 command-line tool that searches for source files
in the current directory (and its subdirectories) based on user-provided glob
patterns and/or tags. The tool aggregates file contents with headers and
copies the result to the clipboard. The search respects ignore files
(e.g., .gitignore) and now supports both inclusion and exclusion of files.

2. FUNCTIONAL REQUIREMENTS
----------------------------
2.1 Command-Line Interface
  - Usage:
      python clip_files.py "<patternOrTag1>" "<patternOrTag2>" ...
  - Inclusion Arguments:
      * Glob Patterns:
          - E.g., "*.js", "*.sh". If an argument lacks a wildcard, it is
            transformed (e.g., "main.py" becomes "*/main.py").
      * Tags:
          - Any argument starting with a plus sign (+) is an inclusion tag
            (e.g., +frontend). Files are scanned for lines containing "tags:"
            with tokens like "#frontend".
  - Exclusion Arguments:
      * Any argument starting with a minus sign (-) is an exclusion.
      * Glob Exclusions:
          - E.g., -*.js excludes files matching that glob.
      * Tag Exclusions:
          - E.g., -+backend excludes files whose first 10 lines contain a tag
            like "#backend".
  - Validation:
      * If no arguments are provided, display a usage message and exit
        with a non-zero status.

2.2 File Discovery
  - The tool performs a recursive filesystem search starting from the
    current directory.
  - Ignore Files:
      * .gitignore or similar files must be respected using an ignore
        processing library (e.g., pathspec).

2.3 File Filtering
  - Inclusion Matching:
      * Normalize file paths (e.g., prefix with "./" if needed).
      * Glob Patterns:
          - Use fnmatch or glob to match file paths against inclusion patterns.
      * Tags:
          - If no glob match and inclusion tags exist, read the first 10 lines
            of a file and use regex to search for tags.
  - Exclusion Matching:
      * For files matching inclusion criteria, apply exclusion rules.
      * Glob Exclusions:
          - Exclude files whose paths match any exclusion glob.
      * Tag Exclusions:
          - Exclude files if their first 10 lines contain any exclusion tag.
  - Unmatched Arguments:
      * Track any inclusion or exclusion arguments that do not match any file,
        and log warnings at the end.

2.4 Output and Clipboard Copy
  - For each final matched file:
      * Log a message (e.g., "📄 Copying file: <filename>").
      * Append a header ("===== <filename> =====") and the file content to an
        aggregate output.
  - Copy the aggregated output to the clipboard using a cross-platform
    library (e.g., pyperclip).
  - Log a summary with the number of files and total character count.

2.5 Error Handling
  - No Files Found:
      * Log a message if no files match the criteria and exit gracefully.
  - File Read Errors:
      * Log errors for unreadable files and continue processing.
  - Invalid Input:
      * Display usage instructions for invalid or missing arguments.

3. NON-FUNCTIONAL REQUIREMENTS
-------------------------------
3.1 Language and Libraries
  - Python 3.x.
  - Standard libraries: os, sys, glob, fnmatch, re.
  - Third-party libraries: pyperclip for clipboard support and pathspec for
    ignore rules.
3.2 Compatibility
  - The tool should work on Unix-like systems and Windows.
3.3 Performance
  - Use efficient directory traversal (os.walk) and limit file reads to the
    first 10 lines.
3.4 Code Quality
  - Ensure a modular design with separate functions for argument parsing,
    file discovery, filtering, output aggregation, and error handling.

4. IMPLEMENTATION DETAILS
-------------------------
4.1 Command-Line Parsing
  - Use sys.argv[1:] to collect arguments.
  - Separate inclusion arguments (glob patterns and tags) from exclusion
    arguments.
  - Transform non-wildcard inclusion patterns as needed.
4.2 File Discovery and Ignore Handling
  - Use os.walk for recursive file search.
  - Apply ignore rules from .gitignore using a library like pathspec.
4.3 File Matching
  - Normalize file paths.
  - Inclusion:
      * Match file paths against inclusion globs and, if needed, inclusion tags.
  - Exclusion:
      * Remove files matching any exclusion glob or containing exclusion tags.
4.4 Output Aggregation and Clipboard Copy
  - Construct output with file headers and full file contents.
  - Use pyperclip to copy the final output to the clipboard.
4.5 Logging and Summary
  - Log each file processed.
  - Report the total number of files processed and the overall character
    count.
  - Warn about any unmatched inclusion or exclusion arguments.

5. TESTING AND VALIDATION
-------------------------
5.1 Unit Tests
  - Validate argument parsing for both inclusion and exclusion.
  - Verify transformation of non-wildcard patterns.
  - Test inclusion and exclusion file matching.
  - Ensure ignore rules are correctly applied.
  - Test clipboard functionality (using stubs or mocks if necessary).
5.2 Manual Testing
  - Run in directories with known files, tags, and ignore configurations.
  - Confirm that exclusion arguments remove the appropriate files.
  - Validate log messages and summary outputs.

6. EXAMPLE USAGE SCENARIOS
--------------------------
Example 1: Matching by Pattern Only
  Command: python clip_files.py "*.py" "*.md"
  - Aggregates all Python and Markdown files (respects .gitignore) and
    copies their contents to the clipboard.

Example 2: Matching by Tag
  Command: python clip_files.py +frontend
  - Aggregates files with "tags: #frontend" in the first 10 lines.

Example 3: Combined Matching with Exclusions
  Command: python clip_files.py +backend "*.json" -*.test.json -+experimental
  - Aggregates JSON files and backend-tagged files, excluding those that match
    *.test.json or contain "#experimental".

Example 4: Exclusion-Only Scenario
  - Files matching inclusion criteria but also matching an exclusion are
    omitted from the output.

===============================================================================
                               VERSION HISTORY
===============================================================================
Version 1.0 : Initial release.
Version 1.1 : Added exclusion support for glob patterns and tags.
===============================================================================
'''
