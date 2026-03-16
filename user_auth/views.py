from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from .models import UserProfile, SubscriptionPlan
from .serializers import RegisterSerializer, UserSerializer, ProfileSerializer
from articulate.utils_streaks import compute_and_update_profile_streaks


def get_suggested_topics(profile):
    """Return topic suggestions based on user profile goal and profession."""
    if not profile:
        return [
            'Job interview',
            'Presentation / pitch',
            'Small talk',
            'Giving feedback',
            'Networking',
            'Phone call',
        ]
    goal = (profile.goal or '').strip().lower()
    profession = (profile.profession or '').strip().lower()
    topics = []
    if goal == 'interview':
        topics = [
            'Job interview',
            'Tell me about yourself',
            'Strengths and weaknesses',
            'Behavioral questions',
            'Salary negotiation',
        ]
    elif goal == 'public_speaking':
        topics = [
            'Presentation / pitch',
            'Opening a speech',
            'Closing a presentation',
            'Q&A handling',
            'Speaking to a group',
        ]
    elif goal == 'confidence':
        topics = [
            'Speaking up in meetings',
            'Small talk',
            'Asking for what you want',
            'Giving your opinion',
            'Handling criticism',
        ]
    elif goal == 'sales':
        topics = [
            'Sales pitch',
            'Objection handling',
            'Closing a deal',
            'Cold call',
            'Product demo',
        ]
    elif goal == 'networking':
        topics = [
            'Networking',
            'Small talk',
            'Elevator pitch',
            'Following up after meeting',
            'LinkedIn / professional intro',
        ]
    elif goal == 'english speaking':
        topics = [
            'English conversation',
            'Daily small talk',
            'Describing your day',
            'Giving directions',
            'Phone call in English',
        ]
    else:
        topics = [
            'Job interview',
            'Presentation / pitch',
            'Small talk',
            'Giving feedback',
            'Networking',
            'Phone call',
        ]
    return topics


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        """Create user, generate OTP, send verification email."""
        user = serializer.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        otp = get_random_string(length=6, allowed_chars='0123456789')
        profile.email_verified = False
        profile.email_otp = otp
        profile.email_otp_expires_at = timezone.now() + timezone.timedelta(minutes=10)
        profile.save(update_fields=["email_verified", "email_otp", "email_otp_expires_at"])

        if user.email:
            subject = "articulate.ai – Verify your email"
            message = (
                f"Welcome to articulate.ai!\n\n"
                f"Your one-time verification code is: {otp}\n\n"
                f"This code will expire in 10 minutes.\n\n"
                f"If you did not request this, you can ignore this email."
            )
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@articulate.ai")
            print("[OTP] Preparing to send email")
            print("[OTP] EMAIL_HOST =", settings.EMAIL_HOST)
            print("[OTP] EMAIL_PORT =", settings.EMAIL_PORT)
            print("[OTP] EMAIL_USE_TLS =", getattr(settings, "EMAIL_USE_TLS", None))
            print("[OTP] EMAIL_HOST_USER =", settings.EMAIL_HOST_USER)
            pwd = settings.EMAIL_HOST_PASSWORD or ""
            print("[OTP] EMAIL_HOST_PASSWORD length =", len(pwd))
            try:
                sent = send_mail(subject, message, from_email, [user.email], fail_silently=False)
                print(f"[OTP] send_mail returned: {sent}")
            except Exception as e:
                print("[OTP] Error sending email:", repr(e))
                # Don't block signup if email fails; frontend can handle lack of email.
                # You can uncomment the next line to surface error to client instead.
                # raise


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]


class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET: return current user's profile (create empty if missing). PUT/PATCH: create or update profile."""
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(
            user=self.request.user,
            defaults={
                'profession': 'student',
                'goal': 'interview',
                'communication_level': 'beginner',
            },
        )
        return profile

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Keep streak numbers in sync whenever profile is fetched.
        streak_data = compute_and_update_profile_streaks(instance)
        serializer = self.get_serializer(instance)
        data = serializer.data
        data['suggested_topics'] = get_suggested_topics(instance)
        data['streak'] = streak_data
        # Profile is considered complete when bio and interests are filled.
        data['has_completed_profile'] = bool(
            (instance.bio and instance.bio.strip())
            and (instance.interests_text and instance.interests_text.strip())
        )
        return Response(data)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user)


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email_otp(request):
    """Verify email using OTP sent during signup."""
    email = (request.data.get("email") or "").strip().lower()
    otp = (request.data.get("otp") or "").strip()
    if not email or not otp:
        return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"error": "User with this email does not exist."}, status=status.HTTP_404_NOT_FOUND)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.email_verified:
        return Response({"message": "Email already verified."}, status=status.HTTP_200_OK)

    now = timezone.now()
    if not profile.email_otp or profile.email_otp_expires_at is None:
        return Response({"error": "No OTP requested. Please sign up again."}, status=status.HTTP_400_BAD_REQUEST)

    if now > profile.email_otp_expires_at:
        return Response({"error": "OTP has expired. Please sign up again."}, status=status.HTTP_400_BAD_REQUEST)

    if otp != profile.email_otp:
        return Response({"error": "Incorrect OTP. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

    profile.email_verified = True
    profile.email_otp = None
    profile.email_otp_expires_at = None
    profile.save(update_fields=["email_verified", "email_otp", "email_otp_expires_at"])

    return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_email_otp(request):
    """Resend a fresh OTP to the given email."""
    email = (request.data.get("email") or "").strip().lower()
    if not email:
        return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"error": "User with this email does not exist."}, status=status.HTTP_404_NOT_FOUND)

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.email_verified:
        return Response({"message": "Email already verified."}, status=status.HTTP_200_OK)

    otp = get_random_string(length=6, allowed_chars='0123456789')
    profile.email_otp = otp
    profile.email_otp_expires_at = timezone.now() + timezone.timedelta(minutes=10)
    profile.save(update_fields=["email_otp", "email_otp_expires_at"])

    if user.email:
        subject = "articulate.ai – Your new verification code"
        message = (
            f"Here is your new one-time verification code for articulate.ai: {otp}\n\n"
            f"This code will expire in 10 minutes."
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@articulate.ai")
        print("[OTP-RESEND] EMAIL_HOST =", settings.EMAIL_HOST)
        print("[OTP-RESEND] EMAIL_HOST_USER =", settings.EMAIL_HOST_USER)
        try:
            sent = send_mail(subject, message, from_email, [user.email], fail_silently=False)
            print(f"[OTP-RESEND] send_mail returned: {sent}")
        except Exception as e:
            print("[OTP-RESEND] Error sending email:", repr(e))
            return Response({"error": "Failed to send email. Check server logs."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"message": "A new code has been sent to your email."}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_subscription_plans(request):
    """Return all subscription plans so frontend can show options."""
    plans = SubscriptionPlan.objects.all().order_by('price')
    data = [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": float(p.price),
            "duration": p.duration,
            "limit_minutes": p.limit_minutes,
        }
        for p in plans
    ]
    return Response({"plans": data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscribe(request):
    """
    Set the user's subscription plan.
    Body: { "plan_id": <SubscriptionPlan.id> }
    """
    plan_id = request.data.get("plan_id")
    if not plan_id:
        return Response({"error": "plan_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.localdate()
    profile.subscription_plan = plan
    profile.subscription_start_date = today
    profile.subscription_expiry = today + timezone.timedelta(days=plan.duration or 30)
    profile.payment_status = "paid" if plan.price > 0 else "unpaid"
    profile.save(update_fields=[
        "subscription_plan",
        "subscription_start_date",
        "subscription_expiry",
        "payment_status",
    ])

    return Response({
        "message": f"Subscribed to {plan.name}",
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "price": float(plan.price),
            "duration": plan.duration,
            "limit_minutes": plan.limit_minutes,
        },
        "subscription_expiry": profile.subscription_expiry,
    })
