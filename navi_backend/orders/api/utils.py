import re


def get_parent_pk(path, parent_tag):
    pattern = rf"/{re.escape(parent_tag)}/(\d+)(?:/|$)"
    match = re.search(pattern, path)
    if match:
        return match.group(1)
    return ""
