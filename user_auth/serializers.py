from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import UserProfile, Badge


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name']

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already exists.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


PROFESSION_CHOICES = [
    ('student', 'Student'),
    ('professional', 'Professional'),
    ('business owner', 'Business Owner'),
]
GOAL_CHOICES = [
    ('interview', 'Interview Preparation'),
    ('public_speaking', 'Public Speaking'),
    ('confidence', 'Confidence Building'),
    ('sales', 'Sales Communication'),
    ('networking', 'Networking'),
    ('english speaking', 'English Speaking'),
]
COMMUNICATION_LEVEL_CHOICES = [
    ('beginner', 'Beginner'),
    ('intermediate', 'Intermediate'),
    ('advanced', 'Advanced'),
]


class ProfileSerializer(serializers.ModelSerializer):
    minutes_limit = serializers.SerializerMethodField()
    minutes_remaining = serializers.SerializerMethodField()
    badge_level = serializers.CharField(read_only=True)
    game_score = serializers.IntegerField(read_only=True)
    current_badge_icon = serializers.SerializerMethodField()
    badge_progress = serializers.SerializerMethodField()
    subscription_active = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id', 'profession', 'goal', 'communication_level', 'bio', 'interests_text',
            'total_sessions', 'total_minutes_spoken', 'average_filler_words', 'average_pace_wpm',
            'confidence_score', 'clarity_score', 'subscription_plan',
            'subscription_expiry', 'payment_status', 'subscription_active',
            'monthly_minutes_used', 'minutes_limit', 'minutes_remaining',
            'current_streak', 'longest_streak', 'total_practice_days',
            'created_at', 'updated_at',
            'badge_level', 'game_score', 'current_badge_icon', 'badge_progress',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'total_sessions',
            'total_minutes_spoken',
            'average_filler_words',
            'average_pace_wpm',
            'confidence_score',
            'clarity_score',
            'subscription_plan',
            'subscription_expiry',
            'payment_status',
            'monthly_minutes_used',
            'current_streak',
            'longest_streak',
            'total_practice_days',
        ]

    def get_subscription_active(self, obj):
        """True only if user has a paid plan that hasn't expired."""
        from django.utils import timezone
        plan = obj.subscription_plan
        today = timezone.now().date()
        if (
            plan is not None
            and obj.payment_status == 'paid'
            and obj.subscription_expiry is not None
            and obj.subscription_expiry >= today
        ):
            return True
        return plan is not None and (obj.payment_status != 'paid' and float(plan.price) == 0)

    def get_minutes_limit(self, obj):
        from django.utils import timezone
        plan = obj.subscription_plan
        today = timezone.now().date()
        if (
            plan is not None
            and obj.payment_status == 'paid'
            and obj.subscription_expiry is not None
            and obj.subscription_expiry >= today
        ):
            return plan.limit_minutes
        return 10

    def get_minutes_remaining(self, obj):
        limit = self.get_minutes_limit(obj)
        used = obj.monthly_minutes_used or 0
        remaining = limit - used
        return remaining if remaining > 0 else 0

    def get_current_badge_icon(self, obj):
        badge = None
        if obj.badge_level and obj.badge_level != "none":
            badge = obj.badges.filter(name__iexact=obj.badge_level).order_by(
                "-score_threshold", "-created_at"
            ).first()
        if badge and badge.icon:
            request = self.context.get("request")
            url = badge.icon.url
            return request.build_absolute_uri(url) if request is not None else url
        return None

    def get_badge_progress(self, obj):
        """Return current score, next threshold, and progress for badge display."""
        badges = {b.name.lower(): b.score_threshold for b in Badge.objects.all()}
        bronze = badges.get("bronze", 0)
        silver = badges.get("silver", 100)
        gold = badges.get("gold", 500)
        diamond = badges.get("diamond", 1000)
        thresholds = [
            ("none", 0),
            ("bronze", bronze),
            ("silver", silver),
            ("gold", gold),
            ("diamond", diamond),
        ]
        current_score = obj.game_score or 0
        level = (obj.badge_level or "none").lower()
        current_threshold = 0
        next_threshold = bronze
        next_badge_name = "Bronze"
        for i, (name, th) in enumerate(thresholds):
            if name == level:
                current_threshold = th
                if i + 1 < len(thresholds):
                    next_threshold = thresholds[i + 1][1]
                    next_badge_name = thresholds[i + 1][0].capitalize()
                else:
                    next_threshold = th
                    next_badge_name = None
                break
        remaining = max(0, next_threshold - current_score) if next_badge_name else 0
        range_size = next_threshold - current_threshold
        progress_pct = (
            min(100, round(100 * (current_score - current_threshold) / range_size))
            if range_size > 0
            else 100
        ) if next_badge_name else 100
        return {
            "current_score": current_score,
            "current_threshold": current_threshold,
            "next_threshold": next_threshold,
            "next_badge_name": next_badge_name,
            "remaining": remaining,
            "progress_pct": progress_pct,
        }
