import re


def clean_text_pageofnum(text):
    lines = text.splitlines()
    cleaned = []
    i = 0
    last_page_num = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        match = re.match(r"^Page\s+(\d+)\s+of\s+(\d+)$", stripped)
        if match:
            last_page_num = int(match.group(1))
            if i + 1 < len(lines) and lines[i + 1].strip().isdigit():
                i += 2
            else:
                i += 1
            continue
        cleaned_line = "".join(c for c in line if c.isprintable() or c in "\n\r\t")
        cleaned.append(cleaned_line)
        i += 1
    return "\n".join(cleaned), last_page_num
