import logging
import re

from django.db import IntegrityError
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from .models import UserProfile, SubscriptionPlan, PaymentOrder


def _send_email(subject, message, to_emails, from_email=None):
    """Send email via Resend (production) or SMTP. Never raises - logs on failure."""
    import logging
    logger = logging.getLogger(__name__)
    from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None) or "onboarding@resend.dev"
    resend_key = getattr(settings, "RESEND_API_KEY", None) or ""
    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            resend_from = getattr(settings, "RESEND_FROM_EMAIL", "onboarding@resend.dev")
            resend.Emails.send({
                "from": resend_from,
                "to": to_emails,
                "subject": subject,
                "text": message,
            })
            return
        except Exception as e:
            logger.exception("Email (Resend) failed: %s", e)
            return
    try:
        send_mail(subject, message, from_email, to_emails, fail_silently=True)
    except Exception as e:
        logger.exception("Email (SMTP) failed: %s", e)
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    ProfileSerializer,
    EmailOrUsernameTokenObtainPairSerializer,
    resolve_user_from_login_identifier,
)
from articulate.utils_streaks import compute_and_update_profile_streaks

logger = logging.getLogger(__name__)


def _unique_username_for_google(email: str, sub: str) -> str:
    """Build a unique Django username from email local-part; never changes existing users."""
    local = email.split("@", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_")[:24] or "user"
    if len(base) < 3:
        base = f"user_{base}"
    candidate = base
    n = 0
    while User.objects.filter(username__iexact=candidate).exists():
        suffix = (sub or "")[-8:] if sub else get_random_string(8)
        candidate = f"{base[:20]}_{suffix}"[:150]
        n += 1
        if n > 50:
            candidate = ("g_" + get_random_string(16))[:150]
            break
    return candidate


@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([JSONParser])
def google_login(request):
    """
    Verify Google ID token, then find User by email (existing accounts keep password unchanged)
    or create a new user with unusable password. Returns SimpleJWT access + refresh.
    """
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "") or ""
    if not client_id:
        return Response(
            {"error": "Google Sign-In is not configured on the server."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    id_token_jwt = (request.data.get("id_token") or "").strip()
    if not id_token_jwt:
        return Response(
            {"error": "id_token is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        request_adapter = google_auth_requests.Request()
        claims = google_id_token.verify_oauth2_token(
            id_token_jwt, request_adapter, client_id
        )
    except Exception as e:
        logger.warning("Google id_token verification failed: %s", e)
        return Response(
            {"error": "Invalid or expired Google token."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    iss = claims.get("iss") or ""
    if iss not in ("https://accounts.google.com", "accounts.google.com"):
        return Response(
            {"error": "Invalid token issuer."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    email = (claims.get("email") or "").strip().lower()
    if not email:
        return Response(
            {"error": "Google account has no email."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not claims.get("email_verified", False):
        return Response(
            {"error": "Google email is not verified."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    sub = (claims.get("sub") or "")[:255]

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        username = _unique_username_for_google(email, sub)
        created = False
        try:
            user = User.objects.create(
                username=username,
                email=email,
                first_name=(claims.get("given_name") or "")[:150],
                last_name=(claims.get("family_name") or "")[:150],
            )
            created = True
        except IntegrityError:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                raise
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])

    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "profession": "student",
            "goal": "interview",
            "communication_level": "beginner",
        },
    )
    if not profile.email_verified:
        profile.email_verified = True
        profile.email_otp = None
        profile.email_otp_expires_at = None
        profile.save(
            update_fields=["email_verified", "email_otp", "email_otp_expires_at"]
        )

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
    )


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

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError as e:
            return Response(
                {"username": ["A user with this username or email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def perform_create(self, serializer):
        """Create user, generate OTP, send verification email."""
        import logging
        logger = logging.getLogger(__name__)
        user = serializer.save()
        try:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            otp = get_random_string(length=6, allowed_chars='0123456789')
            profile.email_verified = False
            profile.email_otp = otp
            profile.email_otp_expires_at = timezone.now() + timezone.timedelta(minutes=10)
            profile.save(update_fields=["email_verified", "email_otp", "email_otp_expires_at"])
        except Exception as e:
            logger.exception("Register: profile create/save failed: %s", e)
            raise

        if user.email:
            subject = "articulate.ai – Verify your email"
            message = (
                f"Welcome to articulate.ai!\n\n"
                f"Your one-time verification code is: {otp}\n\n"
                f"This code will expire in 10 minutes.\n\n"
                f"If you did not request this, you can ignore this email."
            )
            _send_email(subject, message, [user.email])


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = EmailOrUsernameTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            identifier = (request.data.get("username") or "").strip()
            user = resolve_user_from_login_identifier(identifier)
            if user is not None:
                profile = UserProfile.objects.filter(user=user).first()
                if profile and not profile.email_verified:
                    return Response(
                        {
                            "error": "email_not_verified",
                            "email": user.email,
                            "detail": "Please verify your email before logging in.",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
        return response


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
        check_and_expire_subscription(instance)
        instance.refresh_from_db()
        streak_data = compute_and_update_profile_streaks(instance)
        serializer = self.get_serializer(instance, context={"request": request})
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
        instance = serializer.save(user=self.request.user)
        # Auto-assign the free plan when profile is first completed and user has no plan
        if instance.subscription_plan is None:
            has_bio = bool(instance.bio and instance.bio.strip())
            has_interests = bool(instance.interests_text and instance.interests_text.strip())
            if has_bio and has_interests:
                free_plan = SubscriptionPlan.objects.filter(price=0).order_by('id').first()
                if free_plan:
                    _activate_subscription(instance, free_plan)


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
        _send_email(subject, message, [user.email])

    return Response({"message": "A new code has been sent to your email."}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
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


def _activate_subscription(profile, plan):
    """Apply plan to profile: set plan, dates, payment_status, reset monthly usage."""
    today = timezone.localdate()
    profile.subscription_plan = plan
    profile.subscription_start_date = today
    profile.subscription_expiry = today + timezone.timedelta(days=plan.duration or 30)
    profile.payment_status = "paid" if plan.price > 0 else "unpaid"
    profile.monthly_minutes_used = 0
    profile.monthly_minutes_reset_at = today
    profile.save(update_fields=[
        "subscription_plan",
        "subscription_start_date",
        "subscription_expiry",
        "payment_status",
        "monthly_minutes_used",
        "monthly_minutes_reset_at",
    ])


def check_and_expire_subscription(profile):
    """
    If the user's paid subscription has expired, revert them to free mode.
    Call this before any subscription/minutes check.
    Returns True if subscription was expired (user is now free).
    """
    if profile.payment_status != "paid" or profile.subscription_plan is None:
        return False
    today = timezone.localdate()
    if profile.subscription_expiry is not None and profile.subscription_expiry < today:
        profile.subscription_plan = None
        profile.subscription_start_date = None
        profile.subscription_expiry = None
        profile.payment_status = "unpaid"
        profile.monthly_minutes_used = 0
        profile.monthly_minutes_reset_at = today
        profile.save(update_fields=[
            "subscription_plan",
            "subscription_start_date",
            "subscription_expiry",
            "payment_status",
            "monthly_minutes_used",
            "monthly_minutes_reset_at",
        ])
        return True
    return False


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_order(request):
    """
    Create a Razorpay order for a paid subscription plan.
    Body: { "plan_id": <SubscriptionPlan.id> }
    Returns: { "order_id", "amount", "key_id", "plan" }
    """
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not key_id or not key_secret:
        return Response(
            {"error": "Razorpay is not configured. Contact support."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    plan_id = request.data.get("plan_id")
    if not plan_id:
        return Response({"error": "plan_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)

    price = float(plan.price)
    if price <= 0:
        return Response(
            {"error": "Free plans do not require payment. Use subscribe endpoint."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    amount_paise = int(round(price * 100))
    if amount_paise < 100:
        return Response({"error": "Minimum amount is ₹1"}, status=status.HTTP_400_BAD_REQUEST)

    import razorpay
    client = razorpay.Client(auth=(key_id, key_secret))
    receipt = f"plan_{plan_id}_u{request.user.id}_{timezone.now().timestamp():.0f}"[:40]
    data = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": {"plan_id": str(plan_id), "user_id": str(request.user.id)},
    }
    try:
        order = client.order.create(data=data)
    except Exception as e:
        return Response(
            {"error": f"Failed to create order: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    PaymentOrder.objects.create(
        user=request.user,
        plan=plan,
        razorpay_order_id=order["id"],
        amount_paise=amount_paise,
        status="created",
    )

    return Response({
        "order_id": order["id"],
        "amount": order["amount"],
        "key_id": key_id,
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "price": float(plan.price),
            "duration": plan.duration,
            "limit_minutes": plan.limit_minutes,
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """
    Verify Razorpay payment signature and activate subscription.
    Body: {
        "razorpay_payment_id", "razorpay_order_id", "razorpay_signature",
        "plan_id"
    }
    """
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    if not key_secret:
        return Response(
            {"error": "Razorpay is not configured. Contact support."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payment_id = request.data.get("razorpay_payment_id")
    order_id = request.data.get("razorpay_order_id")
    signature = request.data.get("razorpay_signature")
    plan_id = request.data.get("plan_id")

    if not all([payment_id, order_id, signature, plan_id]):
        return Response(
            {"error": "razorpay_payment_id, razorpay_order_id, razorpay_signature, and plan_id are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        plan_id_int = int(plan_id)
    except (TypeError, ValueError):
        return Response({"error": "Invalid plan_id"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = PaymentOrder.objects.get(
            razorpay_order_id=order_id,
            user=request.user,
            plan_id=plan_id_int,
            status="created",
        )
    except PaymentOrder.DoesNotExist:
        return Response({"error": "Order not found or already processed"}, status=status.HTTP_404_NOT_FOUND)

    import razorpay
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
    client = razorpay.Client(auth=(key_id, key_secret))
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
    except Exception as e:
        from razorpay.errors import SignatureVerificationError
        if isinstance(e, SignatureVerificationError):
            return Response({"error": "Invalid payment signature"}, status=status.HTTP_400_BAD_REQUEST)
        raise

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    _activate_subscription(profile, order.plan)

    order.razorpay_payment_id = payment_id
    order.status = "paid"
    order.paid_at = timezone.now()
    order.save(update_fields=["razorpay_payment_id", "status", "paid_at"])

    return Response({
        "message": f"Payment successful. Subscribed to {order.plan.name}",
        "plan": {
            "id": order.plan.id,
            "name": order.plan.name,
            "price": float(order.plan.price),
            "duration": order.plan.duration,
            "limit_minutes": order.plan.limit_minutes,
        },
        "subscription_expiry": profile.subscription_expiry,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscribe(request):
    """
    Set the user's subscription plan (free plans only).
    For paid plans, use create_order + Razorpay checkout + verify_payment.
    Body: { "plan_id": <SubscriptionPlan.id> }
    """
    plan_id = request.data.get("plan_id")
    if not plan_id:
        return Response({"error": "plan_id is required"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)

    if plan.price > 0:
        return Response(
            {"error": "Paid plans require payment. Use the payment flow."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    _activate_subscription(profile, plan)

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
