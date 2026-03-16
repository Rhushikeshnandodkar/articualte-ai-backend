from rest_framework import serializers
from .models import Conversation, ConversationMessage


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ["id", "role", "content", "created_at", "sequence"]


class ConversationListSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id", "topic", "status", "started_at", "ended_at",
            "filler_words_count", "filler_words_breakdown", "pauses_count", "speech_speed_wpm",
            "duration_seconds", "rating", "feedback_summary", "message_count",
        ]

    def get_message_count(self, obj):
        return obj.messages.count()


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = ConversationMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id", "topic", "status", "started_at", "ended_at",
            "filler_words_count", "filler_words_breakdown", "pauses_count", "speech_speed_wpm",
            "duration_seconds", "rating", "feedback_summary", "messages",
        ]


class CreateConversationSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=500, allow_blank=False)
