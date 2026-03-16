from django.contrib import admin
from .models import Conversation, ConversationMessage


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'topic', 'status', 'rating', 'started_at')
    list_filter = ('status', 'rating')
    search_fields = ('topic', 'user__username')
    raw_id_fields = ('user',)


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'role', 'sequence', 'created_at')
    list_filter = ('role',)
    raw_id_fields = ('conversation',)
