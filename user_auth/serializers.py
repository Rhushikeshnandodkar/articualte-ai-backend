from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import UserProfile


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
    class Meta:
        model = UserProfile
        fields = [
            'id', 'profession', 'goal', 'communication_level', 'bio', 'interests_text',
            'total_sessions', 'total_minutes_spoken', 'average_filler_words', 'average_pace_wpm',
            'confidence_score', 'clarity_score', 'subscription_plan',
            'monthly_minutes_used', 'minutes_limit', 'minutes_remaining',
            'current_streak', 'longest_streak', 'total_practice_days',
            'created_at', 'updated_at',
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
            'monthly_minutes_used',
            'current_streak',
            'longest_streak',
            'total_practice_days',
        ]

    def get_minutes_limit(self, obj):
        from django.utils import timezone
        plan = obj.subscription_plan
        today = timezone.now().date()
        # Treat plan as active only if paid and not expired
        if (
            plan is not None
            and obj.payment_status == 'paid'
            and (obj.subscription_expiry is None or obj.subscription_expiry >= today)
        ):
            return plan.limit_minutes
        # Otherwise user is effectively on free plan
        return 10

    def get_minutes_remaining(self, obj):
        limit = self.get_minutes_limit(obj)
        used = obj.monthly_minutes_used or 0
        remaining = limit - used
        return remaining if remaining > 0 else 0
