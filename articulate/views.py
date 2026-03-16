from io import BytesIO
import base64
import tempfile
import os as os_module
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

from user_auth.models import UserProfile

from .models import Conversation, ConversationMessage
from .serializers import (
    ConversationListSerializer,
    ConversationDetailSerializer,
    CreateConversationSerializer,
)
from .utils_stats import compute_conversation_stats
from .utils_streaks import compute_and_update_profile_streaks

import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(settings.BASE_DIR, ".env"))
except ImportError:
    pass


def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Make sure it exists in your environment or .env file."
        )
    return value


def get_llm():
    """Create Groq LLM client (llama-3.3-70b-versatile)."""
    from langchain_groq import ChatGroq
    api_key = _get_env("GROQ_API_KEY")
    return ChatGroq(model_name="llama-3.3-70b-versatile", api_key=api_key)


def get_elevenlabs_client():
    """Create ElevenLabs client for TTS."""
    from elevenlabs.client import ElevenLabs
    api_key = _get_env("ELEVENLABS_API_KEY")
    return ElevenLabs(api_key=api_key)


def build_voice_prompt(topic: str, conversation_history: list) -> str:
    """Build dynamic prompt for this conversation topic and optional history."""
    history_text = ""
    if conversation_history:
        lines = []
        for msg in conversation_history[-10:]:  # last 10 turns
            who = "User" if msg["role"] == "user" else "You"
            lines.append(f"{who}: {msg['content']}")
        history_text = "\n".join(lines) + "\n\n"
    return f"""You are a helpful, friendly coach helping the user practice their communication skills.
Today's topic is strictly: {topic}.

Always keep the conversation focused on this topic. Your follow-up question MUST be clearly about this topic (you can go deeper, ask for examples, stories, opinions, role-plays), but do not switch to unrelated themes.

Reply in exactly two short lines only:
1) one line of thought or brief reaction to what they said, and
2) one open-ended question to keep the conversation going about this topic.

No long explanations, no lists, no extra sentences. Be natural and conversational. Keep each line concise so it's quick to listen to.

{history_text}User said: {{question}}

Your reply (exactly 1 line thought + 1 line open-ended question about this topic):"""


WELCOME_PROMPT = """You are a friendly communication coach. The user is about to start a practice conversation. Generate a short welcome and intro that:
1. Welcomes them and states today's topic clearly.
2. Gives a 2-3 sentence thought or context about the topic to set the scene and spark discussion.
3. Invites them to share when they're ready (e.g. "When you're ready, tell me your thoughts" or "Go ahead and start whenever you like").

Keep it conversational and suitable for being read aloud. No bullet points. Total length: 3-5 sentences.

Topic: {topic}

Your welcome (plain text only):"""


ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"


ELEVENLABS_STT_MODEL = "scribe_v2"


def speech_to_text_elevenlabs(audio_file) -> str:
    """Transcribe audio with ElevenLabs STT (keeps filler words; no_verbatim=False)."""
    client = get_elevenlabs_client()
    if hasattr(audio_file, "read"):
        audio_file.seek(0)
        file_content = audio_file.read()
    else:
        file_content = audio_file
    result = client.speech_to_text.convert(
        file=("audio.webm", file_content, "audio/webm"),
        model_id=ELEVENLABS_STT_MODEL,
        no_verbatim=False,
    )
    if hasattr(result, "text"):
        return (result.text or "").strip()
    if hasattr(result, "transcripts") and result.transcripts:
        return " ".join((t.text or "").strip() for t in result.transcripts).strip()
    return ""


def text_to_speech_elevenlabs(text: str) -> bytes:
    """Convert text to MP3 bytes using ElevenLabs."""
    client = get_elevenlabs_client()
    result = client.text_to_speech.convert(
        text=text,
        voice_id=ELEVENLABS_VOICE_ID,
        model_id=ELEVENLABS_MODEL_ID,
        output_format=ELEVENLABS_OUTPUT_FORMAT,
    )
    buffer = BytesIO()
    for chunk in result:
        buffer.write(chunk)
    buffer.seek(0)
    return buffer.getvalue()



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def conversation_list(request):
    """List current user's conversations (newest first)."""
    qs = Conversation.objects.filter(user=request.user)
    serializer = ConversationListSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def conversation_create(request):
    """Create a new conversation with a topic. User can type topic or select later."""
    ser = CreateConversationSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
    topic = ser.validated_data["topic"].strip()
    if not topic:
        return Response(
            {"error": "Topic cannot be empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    conv = Conversation.objects.create(user=request.user, topic=topic)
    return Response({
        "id": conv.id,
        "topic": conv.topic,
        "status": conv.status,
        "started_at": conv.started_at,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def conversation_detail(request, pk):
    """Get one conversation with full messages and stats."""
    try:
        conv = Conversation.objects.get(pk=pk, user=request.user)
    except Conversation.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    serializer = ConversationDetailSerializer(conv)
    return Response(serializer.data)


def update_user_profile_after_conversation(conv):
    """Update UserProfile with stats from this conversation (sessions, minutes, averages, confidence)."""
    try:
        profile = UserProfile.objects.get(user=conv.user)
    except UserProfile.DoesNotExist:
        return
    profile.total_sessions = (profile.total_sessions or 0) + 1
    duration_min = (conv.duration_seconds or 0) / 60.0
    minutes_this_conv = int(round(duration_min))
    profile.total_minutes_spoken = (profile.total_minutes_spoken or 0) + minutes_this_conv

    # Monthly minutes tracking (reset when a new month starts)
    today = timezone.now().date()
    reset_date = profile.monthly_minutes_reset_at
    if reset_date is None or reset_date.year != today.year or reset_date.month != today.month:
        profile.monthly_minutes_used = 0
        profile.monthly_minutes_reset_at = today
    profile.monthly_minutes_used = (profile.monthly_minutes_used or 0) + minutes_this_conv
    n = profile.total_sessions
    filler = conv.filler_words_count or 0
    profile.average_filler_words = int(
        ((profile.average_filler_words or 0) * (n - 1) + filler) / n
    ) if n else filler
    wpm = conv.speech_speed_wpm or 0
    profile.average_pace_wpm = int(
        ((profile.average_pace_wpm or 0) * (n - 1) + wpm) / n
    ) if n else wpm
    if conv.rating == Conversation.RATING_GOOD:
        profile.confidence_score = min(100, (profile.confidence_score or 0) + 5)
    elif conv.rating == Conversation.RATING_NEEDS_WORK:
        profile.confidence_score = max(0, (profile.confidence_score or 50) - 2)
    elif conv.rating == Conversation.RATING_POOR:
        profile.confidence_score = max(0, (profile.confidence_score or 50) - 5)
    profile.save(
        update_fields=[
            'total_sessions',
            'total_minutes_spoken',
            'monthly_minutes_used',
            'monthly_minutes_reset_at',
            'average_filler_words',
            'average_pace_wpm',
            'confidence_score',
            'updated_at',
        ]
    )

    # Also recompute and persist streak numbers whenever a conversation ends.
    compute_and_update_profile_streaks(profile)


def _get_active_plan_tier(profile: UserProfile) -> str:
    """
    Return 'free', 'builder', or 'performer' based on active subscription.
    A plan is active only if payment_status == 'paid' and not expired.
    """
    today = timezone.now().date()
    plan = profile.subscription_plan
    if (
        plan is not None
        and profile.payment_status == 'paid'
        and (profile.subscription_expiry is None or profile.subscription_expiry >= today)
    ):
        name = (plan.name or "").lower()
        if "builder" in name:
            return "builder"
        if "perform" in name:
            return "performer"
        # Default paid tier behaves like performer (full features)
        return "performer"
    return "free"

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def conversation_end(request, pk):
    """End conversation and compute stats (filler words, pauses, speed, rating). Update user profile."""
    try:
        conv = Conversation.objects.get(pk=pk, user=request.user)
    except Conversation.DoesNotExist:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    if conv.status == Conversation.STATUS_ENDED:
        return Response(ConversationDetailSerializer(conv).data)
    conv.status = Conversation.STATUS_ENDED
    conv.ended_at = timezone.now()
    conv.save()
    compute_conversation_stats(conv)
    conv.refresh_from_db()
    update_user_profile_after_conversation(conv)
    return Response(ConversationDetailSerializer(conv).data)


# ---------- LLM suggested topics from profile ----------

SUGGESTED_TOPICS_PROMPT = """You are a sharp, modern communication coach helping users practice spoken English and real-life conversations.

You must suggest topics that feel **exciting, specific, and emotionally engaging** – things the user would genuinely *want* to talk about, not school-style or textbook topics.

Based on the user's profile below (profession, goal, communication level, interests, and bio), suggest exactly 3 to 5 SPECIFIC, high‑engagement conversation practice topics that would feel natural and interesting for this person.

Strong topics usually:
- are realistic situations they might actually face in their work or real life
- invite opinions, storytelling, or role‑play (e.g. difficult decisions, awkward moments, big opportunities)
- have some tension, stakes, or emotion (e.g. “handling a frustrated client”, “asking for a promotion”, “giving bad news kindly”)
- connect directly to their interests or goals (so they *crave* talking about them)
- include vivid *imagination* scenarios (e.g. “Imagine you are the Prime Minister of India for one day”, “You suddenly meet Elon Musk at a small meetup”)
- include personal favourites or memorable experiences (e.g. “Your favourite book that changed your thinking”, “The most challenging case you handled as a doctor”)

Avoid:
- generic school topics like “environment”, “technology”, “hobbies”, “travel” without a concrete, personal scenario
- bland titles like “Daily routine” or “My city”
- yes/no questions or topics that can be answered in one sentence

Return ONLY a valid JSON array of objects. Each object must have exactly:
- "title": string (short, vivid topic name, e.g. "Imagine you meet Elon Musk at a meetup", "If you were Prime Minister of India for a day")
- "category": string (one word or short label, e.g. "Career", "Leadership", "Favorites", "Experience", "Imagination", "Tech", "Medicine")
- "description": string (short, punchy teaser of 4 to 10 words describing the topic, e.g. "Describe how you’d use one day as PM", "Share a favourite book and why it matters")

User profile:
- Profession: {profession}
- Goal: {goal}
- Communication level: {communication_level}
- Interests: {interests}
- Bio: {bio}

Return only the JSON array of 3-5 objects with title, category, and description:"""


DEFAULT_TOPICS_STRUCTURED = [
    {
        "title": "Imagine you meet Elon Musk at a small meetup",
        "category": "Imagination",
        "description": "Describe the conversation and questions you’d ask",
    },
    {
        "title": "If you were Prime Minister of India for one day",
        "category": "Imagination",
        "description": "Explain your top 2-3 decisions and why",
    },
    {
        "title": "Your favourite book or movie that changed you",
        "category": "Favorites",
        "description": "Share the story and how it impacted your thinking",
    },
    {
        "title": "Handling a really tough situation at work",
        "category": "Experience",
        "description": "Tell a real story with challenges and decisions",
    },
    {
        "title": "Explaining a complex topic in your field to a friend",
        "category": "Career",
        "description": "Practice simplifying something technical or advanced",
    },
]


def _normalize_topic_item(item):
    """Ensure item has title, category, description (strings)."""
    if isinstance(item, str):
        return {"title": item.strip(), "category": "General", "description": "Practice your communication skills."}
    if not isinstance(item, dict):
        return None
    title = (item.get("title") or item.get("name") or "").strip()
    if not title:
        return None
    category = (item.get("category") or item.get("tag") or "General").strip() or "General"
    description = (item.get("description") or item.get("desc") or "Practice your communication skills.").strip()
    if len(description.split()) > 10:
        description = " ".join(description.split()[:8]) + ("..." if len(description.split()) > 8 else "")
    return {"title": title, "category": category, "description": description}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def suggested_topics(request):
    """Get 3-5 personalized topic suggestions from LLM (title, category, description)."""
    import json
    import re
    try:
        profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        return Response({"topics": DEFAULT_TOPICS_STRUCTURED})
    profession = profile.profession or "Not specified"
    goal = profile.goal or "general practice"
    communication_level = profile.communication_level or "beginner"
    interests = (profile.interests_text or "").strip() or "Not specified"
    bio = (profile.bio or "").strip() or "Not specified"
    prompt = SUGGESTED_TOPICS_PROMPT.format(
        profession=profession,
        goal=goal,
        communication_level=communication_level,
        interests=interests,
        bio=bio,
    )
    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        raw = raw.strip()
        array_match = re.search(r"\[[\s\S]*?\]", raw)
        if array_match:
            raw_list = json.loads(array_match.group())
            if isinstance(raw_list, list) and len(raw_list) >= 1:
                topics = []
                for t in raw_list[:6]:
                    normalized = _normalize_topic_item(t)
                    if normalized:
                        topics.append(normalized)
                if topics:
                    return Response({"topics": topics})
        return Response({"topics": DEFAULT_TOPICS_STRUCTURED})
    except Exception:
        return Response({"topics": DEFAULT_TOPICS_STRUCTURED})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def voice_chat(request):
    # Enforce monthly minutes limit before processing voice interaction
    try:
        profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        profile = None
    plan_tier = "free"
    if profile is not None:
        plan_tier = _get_active_plan_tier(profile)
        # Minutes limit: free = 10, paid = plan.limit_minutes
        if plan_tier == "free":
            minutes_limit = 10
        else:
            minutes_limit = profile.subscription_plan.limit_minutes
        used = profile.monthly_minutes_used or 0
        if used >= minutes_limit:
            return Response(
                {
                    "error": "You have used all your practice minutes for this month. Please subscribe or wait for your minutes to reset."
                },
                status=status.HTTP_403_FORBIDDEN,
            )
    raw_cid = request.data.get("conversation_id")
    try:
        conversation_id = int(raw_cid) if raw_cid not in (None, "") else None
    except (TypeError, ValueError):
        conversation_id = None
    want_welcome = request.data.get("welcome") in (True, "true", "1")
    text = (request.data.get("text") or "").strip()
    # Duration (in seconds) that the user's microphone was ON for this turn.
    # The frontend should send this as the time between mic start and mic stop.
    try:
        spoken_duration = float(request.data.get("spoken_duration_seconds", 0) or 0)
    except (TypeError, ValueError):
        spoken_duration = 0.0
    audio_file = request.FILES.get("audio")

    # Welcome: first message from AI when conversation has no messages yet
    if want_welcome and conversation_id and not text and not audio_file:
        try:
            conversation = Conversation.objects.get(
                pk=conversation_id, user=request.user, status=Conversation.STATUS_ACTIVE
            )
        except Conversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if conversation.messages.exists():
            return Response(
                {"error": "Welcome already sent."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        topic = conversation.topic or "general conversation"
        try:
            llm = get_llm()
            prompt = WELCOME_PROMPT.format(topic=topic)
            response = llm.invoke(prompt)
            welcome_text = (response.content if hasattr(response, "content") else str(response)) or (
                f"Welcome! Today we're practicing: {topic}. When you're ready, tell me your thoughts."
            )
            welcome_text = welcome_text.strip()
            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.ROLE_ASSISTANT,
                content=welcome_text,
                sequence=0,
            )
            # For builder plan, do NOT use ElevenLabs TTS – return text only.
            if plan_tier == "builder":
                return Response({"text": welcome_text})
            audio_bytes = text_to_speech_elevenlabs(welcome_text)
            resp = HttpResponse(audio_bytes, content_type="audio/mpeg")
            resp["Content-Length"] = len(audio_bytes)
            resp["X-AI-Response-Text"] = base64.b64encode(welcome_text.encode("utf-8")).decode("ascii")
            resp["Cache-Control"] = "no-cache"
            return resp
        except Exception as e:
            fallback = f"Welcome! Today we're practicing: {topic}. When you're ready, tell me your thoughts."
            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.ROLE_ASSISTANT,
                content=fallback,
                sequence=0,
            )
            # For builder, still avoid TTS even on fallback
            if plan_tier == "builder":
                return Response({"text": fallback})
            try:
                audio_bytes = text_to_speech_elevenlabs(fallback)
                resp = HttpResponse(audio_bytes, content_type="audio/mpeg")
                resp["Content-Length"] = len(audio_bytes)
                resp["X-AI-Response-Text"] = base64.b64encode(fallback.encode("utf-8")).decode("ascii")
                resp["Cache-Control"] = "no-cache"
                return resp
            except Exception:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if audio_file:
        try:
            text = speech_to_text_elevenlabs(audio_file)
            print(f"[Voice] Transcribed (ElevenLabs STT): {text!r}")
        except Exception as e:
            print(f"[Voice] STT error: {e}")
            return Response(
                {"error": f"Speech-to-text failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    print(f"[Voice] User said: {text!r} (conversation_id={conversation_id})")
    if not text:
        return Response(
            {"error": "Missing or empty text. Say something and click Pause, or send audio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation = None
    topic = "general conversation"
    history = []

    if conversation_id:
        try:
            conversation = Conversation.objects.get(
                pk=conversation_id, user=request.user, status=Conversation.STATUS_ACTIVE
            )
            topic = conversation.topic
            history = [
                {"role": m.role, "content": m.content}
                for m in conversation.messages.order_by("sequence")[:20]
            ]
        except Conversation.DoesNotExist:
            pass

    try:
        llm = get_llm()
        prompt_template = build_voice_prompt(topic, history)
        prompt = prompt_template.format(question=text)
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)
        if not response_text:
            response_text = "I didn't catch that. Could you say it again?"
        print(f"[Voice] AI response: {response_text!r}")

        if conversation:
            next_seq = conversation.messages.count()
            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.ROLE_USER,
                content=text,
                sequence=next_seq,
                spoken_duration_seconds=spoken_duration if spoken_duration > 0 else None,
            )
            ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.ROLE_ASSISTANT,
                content=response_text,
                sequence=next_seq + 1,
            )

        # Builder plan: STT allowed, but NO TTS (text-only reply).
        if plan_tier == "builder":
            return Response({"text": response_text})

        audio_bytes = text_to_speech_elevenlabs(response_text)
        print(f"[Voice] ElevenLabs audio size: {len(audio_bytes)} bytes")
        resp = HttpResponse(audio_bytes, content_type="audio/mpeg")
        resp["Content-Length"] = len(audio_bytes)
        resp["X-AI-Response-Text"] = base64.b64encode(response_text.encode("utf-8")).decode("ascii")
        resp["Cache-Control"] = "no-cache"
        return resp
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

REPHRASE_PROMPT = """You are a communication coach. The user said the following in a practice conversation. Your job is to rephrase their answer to make it clearer, more professional, and easier to understand—while keeping their meaning and intent.

User's answer:
{text}

Respond with ONLY a valid JSON object (no other text), in this exact format:
{{"rephrased": "your improved version of their answer in one or two clear sentences", "explanation": "1-2 sentences explaining what you changed and why it sounds better (e.g. 'Used stronger verbs' or 'Made the structure clearer')"}}
"""


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def rephrase(request):
    """Take user's transcript text and return a better, rephrased version with short explanation."""
    import json
    import re
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response(
            {"error": "Missing 'text' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        llm = get_llm()
        prompt = REPHRASE_PROMPT.format(text=text)
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        raw = raw.strip()
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            data = json.loads(json_match.group())
            return Response({
                "original": text,
                "rephrased": data.get("rephrased", raw),
                "explanation": data.get("explanation", ""),
            })
        return Response({
            "original": text,
            "rephrased": raw,
            "explanation": "",
        })
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


GRAMMAR_PROMPT = """You are an English grammar coach. Analyze the following text for grammatical mistakes. Be clear and educational so the user can understand what they got wrong.

User's text:
{text}

Respond with ONLY a valid JSON object (no other text), in this exact format:
{{
  "mistakes": [
    {{ "wrong": "exact phrase they said that is wrong", "correct": "corrected version", "rule": "short explanation (e.g. 'Use past tense for completed actions')" }}
  ],
  "corrected_sentence": "the full sentence(s) with all corrections applied",
  "summary": "1-3 sentences: what this user tends to get confused about (e.g. tense, articles, subject-verb agreement) and a brief tip to improve"
}}

If there are no grammatical mistakes, return: {{ "mistakes": [], "corrected_sentence": "<repeat the user's text unchanged>", "summary": "No grammar mistakes found. Good job!" }}
"""


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def grammar_check(request):
    import json
    import re
    import ast
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response(
            {"error": "Missing 'text' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        llm = get_llm()
        prompt = GRAMMAR_PROMPT.format(text=text)
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        raw = raw.strip()
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            fragment = json_match.group()
            try:
                data = json.loads(fragment)
            except json.JSONDecodeError:
                # LLM sometimes returns Python-style dicts (single quotes, etc.).
                # Fall back to ast.literal_eval to parse those safely, but guard against syntax errors.
                try:
                    data = ast.literal_eval(fragment)
                except (ValueError, SyntaxError):
                    data = {}
            mistakes = data.get("mistakes") or []
            return Response({
                "original": text,
                "mistakes": mistakes,
                "mistake_count": len(mistakes),
                "corrected_sentence": data.get("corrected_sentence", text),
                "summary": data.get("summary", ""),
            })
        return Response({
            "original": text,
            "mistakes": [],
            "mistake_count": 0,
            "corrected_sentence": text,
            "summary": raw or "Could not parse analysis.",
        })
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
