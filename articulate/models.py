from django.db import models
from django.contrib.auth.models import User


class Conversation(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_CHOICES = [(STATUS_ACTIVE, "Active"), (STATUS_ENDED, "Ended")]

    RATING_GOOD = "good"
    RATING_NEEDS_WORK = "needs_work"
    RATING_POOR = "poor"
    RATING_CHOICES = [
        (RATING_GOOD, "Good"),
        (RATING_NEEDS_WORK, "Needs work"),
        (RATING_POOR, "Poor"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="articulate_conversations")
    topic = models.CharField(max_length=500, help_text="What the user wants to practice (e.g. job interview, presentation).")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    # Stats computed when conversation ends (for beginners improving communication)
    filler_words_count = models.IntegerField(null=True, blank=True, help_text="Count of um, uh, like, etc.")
    pauses_count = models.IntegerField(null=True, blank=True, help_text="Number of noticeable pauses.")
    speech_speed_wpm = models.FloatField(null=True, blank=True, help_text="Words per minute (user speech).")
    duration_seconds = models.FloatField(null=True, blank=True, help_text="Total conversation duration in seconds.")
    rating = models.CharField(
        max_length=20, choices=RATING_CHOICES, null=True, blank=True,
        help_text="Overall: good / needs_work / poor."
    )
    feedback_summary = models.TextField(
        blank=True,
        help_text="Short feedback for the user on how to improve.",
    )
    filler_words_breakdown = models.JSONField(
        null=True,
        blank=True,
        help_text="Per-word filler count e.g. {\"um\": 5, \"like\": 3}.",
    )

    class Meta:
        ordering = ["-started_at"]


class ConversationMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "User"), (ROLE_ASSISTANT, "Assistant")]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    spoken_duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Approx seconds user was speaking for this turn (mic-on time).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sequence = models.IntegerField(default=0, help_text="Order of turn in conversation.")

    class Meta:
        ordering = ["conversation", "sequence"]

