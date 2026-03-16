import re
from datetime import timedelta
from .models import Conversation, ConversationMessage


# Common filler words (case-insensitive word boundaries)
FILLER_PATTERNS = [
    r"\bum\b",
    r"\buh\b",
    r"\buhm\b",
    r"\blike\b",  # can overcount; use as rough metric
    r"\byou know\b",
    r"\bactually\b",
    r"\bbasically\b",
    r"\bliterally\b",
    r"\bso\b",  # often filler at start of sentence; optional
    r"\bwell\b",
    r"\ber\b",
    r"\bah\b",
]

# Filler words we count (include variations for report)
FILLER_WORDS = ["um", "uh", "uhm", "you know", "actually", "basically", "well", "er", "ah", "like"]


def count_filler_words(text: str) -> int:
    if not text:
        return 0
    text_lower = text.lower()
    count = 0
    for word in FILLER_WORDS:
        count += len(re.findall(r"\b" + re.escape(word) + r"\b", text_lower))
    return count


def get_filler_breakdown(text: str) -> dict:
    """Return dict of filler word -> count for report."""
    if not text:
        return {}
    text_lower = text.lower()
    breakdown = {}
    for word in FILLER_WORDS:
        n = len(re.findall(r"\b" + re.escape(word) + r"\b", text_lower))
        if n > 0:
            breakdown[word] = n
    return breakdown


def compute_conversation_stats(conversation: Conversation) -> None:
    """Compute filler words, pauses, speech speed, rating and save on conversation."""
    user_messages = list(
        conversation.messages.filter(role=ConversationMessage.ROLE_USER).order_by("sequence")
    )
    if not user_messages:
        # No explicit user messages saved. Still record a duration based on
        # the session lifetime (started_at -> ended_at) so minutes are counted.
        from django.utils import timezone

        start = conversation.started_at
        end = conversation.ended_at or timezone.now()
        duration_seconds = (end - start).total_seconds() if start else 0
        if duration_seconds < 1:
            duration_seconds = 1.0

        conversation.filler_words_count = 0
        conversation.pauses_count = 0
        conversation.speech_speed_wpm = None
        conversation.duration_seconds = round(duration_seconds, 1)
        conversation.rating = Conversation.RATING_NEEDS_WORK
        conversation.feedback_summary = "No speech was recorded. Try again and say a few sentences."
        conversation.save()
        return

    # Filler words and breakdown for report
    total_fillers = 0
    breakdown_combined = {}
    for m in user_messages:
        total_fillers += count_filler_words(m.content)
        for word, cnt in get_filler_breakdown(m.content).items():
            breakdown_combined[word] = breakdown_combined.get(word, 0) + cnt
    conversation.filler_words_count = total_fillers
    conversation.filler_words_breakdown = breakdown_combined if breakdown_combined else None

    # Pauses: gaps between consecutive user messages > 2.5 seconds
    pause_threshold_seconds = 2.5
    pauses = 0
    for i in range(1, len(user_messages)):
        prev = user_messages[i - 1].created_at
        curr = user_messages[i].created_at
        if (curr - prev).total_seconds() > pause_threshold_seconds:
            pauses += 1
    conversation.pauses_count = pauses

    # Duration: prefer mic-on time (spoken_duration_seconds) if provided,
    # otherwise fall back to first/last timestamp difference.
    total_spoken_seconds = 0.0
    has_spoken_durations = False
    for m in user_messages:
        if getattr(m, "spoken_duration_seconds", None):
            total_spoken_seconds += float(m.spoken_duration_seconds or 0)
            has_spoken_durations = True

    if has_spoken_durations and total_spoken_seconds > 0:
        duration_seconds = total_spoken_seconds
    else:
        first_ts = user_messages[0].created_at
        last_ts = user_messages[-1].created_at
        duration_seconds = (last_ts - first_ts).total_seconds()

    if duration_seconds < 1:
        duration_seconds = 1.0
    conversation.duration_seconds = round(duration_seconds, 1)

    # Words per minute (user only, using duration_seconds above)
    total_words = sum(len(m.content.split()) for m in user_messages)
    duration_minutes = duration_seconds / 60.0
    wpm = total_words / duration_minutes if duration_minutes > 0 else None
    conversation.speech_speed_wpm = round(wpm, 1) if wpm is not None else None

    # Rating: simple rules for beginners
    rating = Conversation.RATING_GOOD
    feedback_parts = []

    if total_fillers > 15:
        rating = Conversation.RATING_NEEDS_WORK
        breakdown_str = ", ".join(f"'{w}': {c}" for w, c in sorted(breakdown_combined.items(), key=lambda x: -x[1]))
        feedback_parts.append(f"You used {total_fillers} filler words ({breakdown_str}). Try pausing briefly instead of saying them.")
    elif total_fillers > 8:
        breakdown_str = ", ".join(f"'{w}': {c}" for w, c in sorted(breakdown_combined.items(), key=lambda x: -x[1]))
        feedback_parts.append(f"You had {total_fillers} filler words ({breakdown_str}). Reducing them will make you sound more confident.")

    if wpm is not None:
        if wpm < 100:
            feedback_parts.append(f"Your pace was a bit slow ({wpm:.0f} words/min). Try speaking a little faster.")
        elif wpm > 180:
            rating = Conversation.RATING_NEEDS_WORK if rating != Conversation.RATING_POOR else rating
            feedback_parts.append(f"Your pace was quite fast ({wpm:.0f} words/min). Slowing down can help clarity.")

    if pauses > 10:
        feedback_parts.append(f"You had {pauses} noticeable pauses. Short pauses are fine; long silences can be reduced with practice.")

    if rating == Conversation.RATING_GOOD and not feedback_parts:
        feedback_parts.append("Good job! Keep practicing to build confidence.")

    conversation.rating = rating
    conversation.feedback_summary = " ".join(feedback_parts) if feedback_parts else "Keep practicing!"
    conversation.save()
