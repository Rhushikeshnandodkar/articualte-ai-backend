from django.urls import path
from . import views

urlpatterns = [
    path("topics/", views.topic_list, name="topic_list"),
    path("voice/", views.voice_chat, name="voice_chat"),
    path("talking-agent/start/", views.talking_agent_start, name="talking_agent_start"),
    path("talking-agent/voice/", views.talking_agent_voice, name="talking_agent_voice"),
    path("suggested-topics/", views.suggested_topics, name="suggested_topics"),
    path("daily-topic/", views.daily_topic, name="daily_topic"),
    path("rephrase/", views.rephrase, name="rephrase"),
    path("grammar-check/", views.grammar_check, name="grammar_check"),
    path("conversations/", views.conversation_list, name="conversation_list"),
    path("conversations/create/", views.conversation_create, name="conversation_create"),
    path("conversations/<int:pk>/", views.conversation_detail, name="conversation_detail"),
    path("conversations/<int:pk>/end/", views.conversation_end, name="conversation_end"),
]
