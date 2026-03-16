from rest_framework import serializers
from .models import Conversation, ConversationMessage, Topic, TopicProgress


class TopicSerializer(serializers.ModelSerializer):
    best_score = serializers.SerializerMethodField()
    attempts = serializers.SerializerMethodField()
    completed = serializers.SerializerMethodField()
    last_score = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = [
            "id",
            "title",
            "category",
            "level",
            "description",
            "time_limit_seconds",
            "is_active",
            "created_at",
            "best_score",
            "attempts",
            "completed",
            "last_score",
        ]

    def _get_progress(self, obj):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        try:
            return TopicProgress.objects.get(user=request.user, topic=obj)
        except TopicProgress.DoesNotExist:
            return None

    def get_best_score(self, obj):
        progress = self._get_progress(obj)
        return progress.best_score if progress is not None else 0

    def get_attempts(self, obj):
        progress = self._get_progress(obj)
        return progress.attempts if progress is not None else 0

    def get_completed(self, obj):
        progress = self._get_progress(obj)
        return bool(progress and progress.best_score > 0)

    def get_last_score(self, obj):
        progress = self._get_progress(obj)
        return progress.last_score if progress is not None else 0


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ["id", "role", "content", "created_at", "sequence"]


class ConversationListSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "topic",
            "status",
            "started_at",
            "ended_at",
            "filler_words_count",
            "filler_words_breakdown",
            "pauses_count",
            "speech_speed_wpm",
            "duration_seconds",
            "rating",
            "feedback_summary",
            "message_count",
        ]

    def get_message_count(self, obj):
        return obj.messages.count()


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = ConversationMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "topic",
            "status",
            "started_at",
            "ended_at",
            "filler_words_count",
            "filler_words_breakdown",
            "pauses_count",
            "speech_speed_wpm",
            "duration_seconds",
            "rating",
            "feedback_summary",
            "messages",
        ]


class CreateConversationSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=500, allow_blank=False)
