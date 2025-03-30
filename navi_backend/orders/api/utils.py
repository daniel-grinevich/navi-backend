import re


def getParentPK(path, parentTag):
    pattern = rf"/{re.escape(parentTag)}/(\d+)(?:/|$)"
    match = re.search(pattern, path)
    if match:
        return match.group(1)
    return ""
