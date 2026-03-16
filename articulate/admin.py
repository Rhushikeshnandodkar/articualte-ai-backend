from django.contrib import admin
from .models import Conversation, ConversationMessage, Topic, TopicProgress


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "level", "is_active", "created_at")
    list_filter = ("level", "category", "is_active")
    search_fields = ("title", "category", "description")


@admin.register(TopicProgress)
class TopicProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "topic", "best_score", "attempts", "last_completed_at")
    list_filter = ("topic__category",)
    search_fields = ("user__username", "topic__title")
    raw_id_fields = ("user", "topic")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "topic", "status", "rating", "started_at")
    list_filter = ("status", "rating")
    search_fields = ("topic", "user__username")
    raw_id_fields = ("user",)


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "sequence", "created_at")
    list_filter = ("role",)
    raw_id_fields = ("conversation",)
