def to_markdown_v2(blocks):

    md = ""

    for b in blocks:

        text = "".join(b["text"])

        if b["type"] == "title":
            md += f"# {text}\n\n"

        elif b["type"] == "table":
            md += f"📊 TABLE:\n{text}\n\n"

        elif b["type"] == "figure":
            md += f"🖼 FIGURE\n\n"

        else:
            md += f"{text}\n\n"

    return md