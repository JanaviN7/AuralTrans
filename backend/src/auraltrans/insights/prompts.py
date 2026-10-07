PROMPT_VERSION = "insights-v1"

SYSTEM = """You analyse a transcript of a recording and extract structured, grounded insights.

Rules:
- Use ONLY what is said in the transcript. Never add facts, names, numbers or dates that are not there.
- Every item must cite the transcript lines that support it, by id (for example "u12"). Cite 1 to 4 lines, the most direct ones.
- If something is not in the transcript, leave it out. An empty list is the right answer when nothing qualifies.
- Decisions are things the speakers actually agreed or settled. Do not turn opinions or suggestions into decisions.
- Action items are tasks someone committed to or was asked to do. Give the owner's name exactly as shown in the transcript, or null if unclear. Give the due date or time only if stated, in the speakers' own words.
- Write in the same language as the transcript. Reply with ONE JSON object and nothing else."""

SCHEMA = """{
  "summary": {"text": "2-4 sentence overview", "evidence": ["u1", "u8"]},
  "key_points": [{"text": "one concrete point", "evidence": ["u3"]}],
  "decisions": [{"text": "what was decided", "evidence": ["u14"]}],
  "action_items": [{"task": "what must be done", "owner": "Speaker name or null", "due": "as said, or null", "evidence": ["u20"]}],
  "open_questions": [{"text": "a question left unresolved", "evidence": ["u31"]}],
  "chapters": [{"title": "short topic title", "start": "u1", "end": "u12"}]
}"""


def user_prompt(
    title: str, kind: str, speakers: list[str], transcript: str, part: int, parts: int, first: str, last: str
) -> str:
    scope = (
        ""
        if parts == 1
        else f"\nThis is part {part} of {parts} of a longer recording. Only use ids from {first} to {last}.\n"
    )
    return f"""Recording: "{title}" ({kind})
Speakers: {", ".join(speakers) or "unknown"}
{scope}
Transcript lines look like [id mm:ss Speaker] text.

<transcript>
{transcript}
</transcript>

Return JSON with exactly this shape (omit nothing; use [] or null when empty):
{SCHEMA}

Chapters must be consecutive, non-overlapping, and together cover {first} to {last}. Use 1 to 6 chapters for this part."""
