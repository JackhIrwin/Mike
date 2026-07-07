"""Builds the morning to-do text: upcoming deadlines + anything still pending
a reply from a third party. Deliberately deterministic (no LLM call) so the
list itself is never paraphrased or hallucinated — accuracy matters more than
flourish for a daily to-do."""

import db


def build_digest_text() -> str:
    deadlines = db.get_upcoming_deadlines(days_ahead=7)
    open_tasks = db.get_all_open_tasks()

    lines = ["Morning — here's what's on deck:"]

    if deadlines:
        lines.append("\n📌 Deadlines (next 7 days):")
        for d in deadlines:
            tag = f" ({d['client_name']})" if d.get("client_name") else ""
            lines.append(f"- {d['due_date']}: {d['description']}{tag}")
    else:
        lines.append("\n📌 No deadlines in the next 7 days.")

    if open_tasks:
        lines.append("\n⏳ Still waiting to hear back:")
        for t in open_tasks:
            tag = f" ({t['client_name']})" if t.get("client_name") else ""
            lines.append(f"- {t['purpose']}{tag} — {t['party_phone']}")

    return "\n".join(lines)
