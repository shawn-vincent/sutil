#!/usr/bin/env python3
# sutil/clip_files.py
# tags: #util #clipboard 
"""
clip_files.py - Aggregate file contents based on glob patterns and tags,
                supporting both inclusion and exclusion rules. Supports the
                optional flag "--no-ignore" to ignore .gitignore exclusions and
                "--no-headers" to suppress header lines in the output.

Usage:
    python clip_files.py [--no-ignore] [--no-headers] "<patternOrTag1>" "<patternOrTag2>" ...

Examples:
    python clip_files.py "*.py" "*.md"
    python clip_files.py --no-ignore "*.py" "*.md"
    python clip_files.py --no-headers +frontend "*.json" -*.test.json -+experimental
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
        "Usage: python clip_files.py [--no-ignore] [--no-headers] \"<patternOrTag1>\" \"<patternOrTag2>\" ...\n"
        "\n"
        "Optional Flags:\n"
        "  --no-ignore    Do not apply .gitignore exclusions (include all files).\n"
        "  --no-headers   Suppress output headers before each file in the aggregated content.\n"
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
            line = line.rstrip()
            if not line:
                continue  # blank line
            if line.lstrip().startswith('#'):
                continue

            negated = False
            if line.startswith('!'):
                negated = True
                line = line[1:]
            anchored = False
            if line.startswith('/'):
                anchored = True
                line = line[1:]
            directory_only = False
            if line.endswith('/'):
                directory_only = True
            test_pattern = line[:-1] if directory_only else line
            if not anchored and '/' not in test_pattern:
                line = '**/' + line
            if directory_only and not line.endswith('/**'):
                line = line + '**'
            if negated:
                line = '!' + line
            processed_patterns.append(line)

        try:
            return pathspec.PathSpec.from_lines('gitwildmatch', processed_patterns)
        except Exception as e:
            print(f"⚠️ Warning: Could not compile ignore spec: {e}", file=sys.stderr)
    return None


def parse_arguments(args):
    """
    Parse command-line arguments into inclusion and exclusion categories.
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
            if len(arg) > 1 and arg[1] == '+':
                tag = arg[2:]
                exclusion_tags.append(tag)
                unmatched_exclusion_tags.append(tag)
            else:
                pattern = arg[1:]
                exclusion_patterns.append(pattern)
                unmatched_exclusion_patterns.append(pattern)
        else:
            if arg.startswith('+'):
                tag = arg[1:]
                inclusion_tags.append(tag)
                unmatched_inclusion_tags.append(tag)
            else:
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
    """
    matched = False
    used_pattern = None
    used_tag = None
    lines = None

    for pattern in arg_data['inclusion_patterns']:
        if fnmatch.fnmatch(file_path, pattern):
            matched = True
            used_pattern = pattern
            break

    if not matched and arg_data['inclusion_tags']:
        try:
            with open(file_path, 'r', errors='replace') as f:
                lines = [f.readline() for _ in range(10)]
                content = "".join(lines)
        except Exception as e:
            print(f"❌ Error reading file {file_path}: {e}", file=sys.stderr)
            return (False, None, None, lines)

        for tag in arg_data['inclusion_tags']:
            if re.search(r"tags:.*#" + re.escape(tag) + r"\b", content):
                matched = True
                used_tag = tag
                break

    return (matched, used_pattern, used_tag, lines)


def file_matches_exclusion(file_path, arg_data, lines_cache):
    """
    Check if file_path should be excluded based on exclusion glob patterns or tags.
    """
    for pattern in arg_data['exclusion_patterns']:
        if fnmatch.fnmatch(file_path, pattern):
            return (pattern, None)

    if arg_data['exclusion_tags']:
        content = ""
        if lines_cache is None:
            try:
                with open(file_path, 'r', errors='replace') as f:
                    lines = [f.readline() for _ in range(10)]
                    content = "".join(lines)
            except Exception as e:
                print(f"❌ Error reading file {file_path}: {e}", file=sys.stderr)
        else:
            content = "".join(lines_cache)
        for tag in arg_data['exclusion_tags']:
            if re.search(r"tags:.*#" + re.escape(tag) + r"\b", content):
                return (None, tag)

    return (None, None)


def main():
    args = sys.argv[1:]
    
    # Process flag: --no-ignore
    no_ignore = False
    if "--no-ignore" in args:
        no_ignore = True
        args.remove("--no-ignore")
    
    # Process new flag: --no-headers
    no_headers = False
    if "--no-headers" in args:
        no_headers = True
        args.remove("--no-headers")
    
    if not args:
        print_usage()
        sys.exit(1)

    arg_data = parse_arguments(args)

    ignore_spec = None
    if not no_ignore:
        ignore_spec = load_ignore_spec()

    candidate_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            file_path = os.path.join(root, file)
            if not (file_path.startswith('./') or file_path.startswith('/')):
                file_path = "./" + file_path
            if ignore_spec:
                rel_path = os.path.relpath(file_path, os.getcwd())
                if ignore_spec.match_file(rel_path):
                    continue
            candidate_files.append(file_path)

    if not candidate_files:
        print("⚠️ No candidate files found in the filesystem.")
        sys.exit(0)

    final_files = []
    for file in candidate_files:
        include_match, used_incl_pattern, used_incl_tag, lines_cache = file_matches_inclusion(file, arg_data)
        if not include_match:
            continue

        if used_incl_pattern and used_incl_pattern in arg_data['unmatched_inclusion_patterns']:
            arg_data['unmatched_inclusion_patterns'].remove(used_incl_pattern)
        if used_incl_tag and used_incl_tag in arg_data['unmatched_inclusion_tags']:
            arg_data['unmatched_inclusion_tags'].remove(used_incl_tag)

        ex_pattern, ex_tag = file_matches_exclusion(file, arg_data, lines_cache)
        if ex_pattern or ex_tag:
            if ex_pattern and ex_pattern in arg_data['unmatched_exclusion_patterns']:
                arg_data['unmatched_exclusion_patterns'].remove(ex_pattern)
            if ex_tag and ex_tag in arg_data['unmatched_exclusion_tags']:
                arg_data['unmatched_exclusion_tags'].remove(ex_tag)
            continue

        final_files.append(file)

    if not final_files:
        print("⚠️ No files matched the given patterns/tags after applying exclusions.")
        sys.exit(0)

    aggregated_output = ""
    file_count = 0
    for file in final_files:
        print(f"📄 Copying file: {file}")
        file_count += 1
        if not no_headers:
            aggregated_output += f"===== {file} =====\n"
        try:
            with open(file, 'r', errors='replace') as f:
                aggregated_output += f.read() + "\n"
        except Exception as e:
            print(f"❌ Error reading file {file}: {e}", file=sys.stderr)

    try:
        pyperclip.copy(aggregated_output)
    except Exception as e:
        print(f"❌ Error copying to clipboard: {e}", file=sys.stderr)

    char_count = len(aggregated_output)
    print(f"✅ Copied {file_count} files ({char_count} characters) to the clipboard.")

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
