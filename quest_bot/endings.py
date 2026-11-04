def report(opened, content):
    lines = [f"Открыто {len(opened)} из {len(content.endings)}"]
    lines.extend(f"{ending_id}. {content.endings[ending_id]}" for ending_id in sorted(opened))
    return "\n".join(lines)
