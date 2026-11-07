def report(opened, content):
    heading = f"Открыто {len(opened)} из {len(content.endings)}"
    if not opened:
        return heading
    lines = [f"{ending_id}. {content.endings[ending_id]}" for ending_id in sorted(opened)]
    return heading + "\n\n" + "\n".join(lines)
