from django.urls import path
from . import views

urlpatterns = [
    path("voice/", views.voice_chat, name="voice_chat"),
    path("suggested-topics/", views.suggested_topics, name="suggested_topics"),
    path("rephrase/", views.rephrase, name="rephrase"),
    path("grammar-check/", views.grammar_check, name="grammar_check"),
    path("conversations/", views.conversation_list, name="conversation_list"),
    path("conversations/create/", views.conversation_create, name="conversation_create"),
    path("conversations/<int:pk>/", views.conversation_detail, name="conversation_detail"),
    path("conversations/<int:pk>/end/", views.conversation_end, name="conversation_end"),
]
