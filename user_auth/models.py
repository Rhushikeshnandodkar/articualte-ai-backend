from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
# Create your models here.
class Interest(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.IntegerField(default=30)
    limit_minutes = models.IntegerField(default=300, help_text="Monthly practice minutes included")


class PaymentOrder(models.Model):
    """Tracks Razorpay orders for subscription payments."""
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    amount_paise = models.IntegerField(help_text="Amount in paise (INR)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Order'
        verbose_name_plural = 'Payment Orders'

class Badge(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    icon = models.FileField(upload_to="badges/", null=True, blank=True)
    score_threshold = models.IntegerField(
        default=0,
        help_text="Minimum game_score required to earn this badge.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Badge'
        verbose_name_plural = 'Badges'  

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    interests = models.ManyToManyField(Interest, related_name='users', blank=True)
    interests_text = models.CharField(max_length=500, blank=True, help_text="Comma-separated interests e.g. technology, sales, interviews")
    bio = models.TextField(null=True, blank=True)
    communication_level = models.CharField(max_length=255, choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')], default='beginner')
    profession = models.CharField(max_length=255, choices=[('student', 'Student'), ('professional', 'Professional'), ('business owner', 'Business Owner')], default='student')
    total_sessions = models.IntegerField(default=0)
    total_minutes_spoken = models.IntegerField(default=0)
    average_filler_words = models.IntegerField(default=0)
    average_pace_wpm = models.IntegerField(default=0)
    average_pause_duration = models.IntegerField(default=0)
    confidence_score = models.IntegerField(default=0)
    clarity_score = models.IntegerField(default=0)
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, null=True, blank=True)
    subscription_start_date = models.DateField(null=True, blank=True)
    subscription_expiry = models.DateField(null=True, blank=True)
    payment_status = models.CharField(max_length=255, choices=[('paid', 'Paid'), ('unpaid', 'Unpaid')], default='unpaid')
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    total_practice_days = models.IntegerField(default=0)
    badges = models.ManyToManyField(Badge, related_name='users', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    # Monthly usage tracking (for subscription minutes)
    monthly_minutes_used = models.IntegerField(default=0, help_text="Minutes spoken in current billing month")
    monthly_minutes_reset_at = models.DateField(null=True, blank=True, help_text="Date when monthly minutes were last reset")
    goal = models.CharField(
    max_length=255,
    choices=[
        ('interview', 'Interview Preparation'),
        ('public_speaking', 'Public Speaking'),
        ('confidence', 'Confidence Building'),
        ('sales', 'Sales Communication'), 
        ('networking', 'Networking'),
        ('english speaking', 'English Speaking'),
    ],
    null=True,
    blank=True,
    default='interview'
    )
    # Email verification / OTP
    email_verified = models.BooleanField(default=False)
    email_otp = models.CharField(max_length=6, null=True, blank=True)
    email_otp_expires_at = models.DateTimeField(null=True, blank=True)
    # Daily practice topic (one per day per user)
    daily_topic_title = models.CharField(max_length=255, null=True, blank=True)
    daily_topic_description = models.TextField(null=True, blank=True)
    daily_topic_date = models.DateField(null=True, blank=True, help_text="Date when daily topic was generated")
    # Gamified score & badge for table topics
    game_score = models.IntegerField(default=0, help_text="Gamified score from completed table topics")
    badge_level = models.CharField(
        max_length=20,
        choices=[
            ("none", "None"),
            ("bronze", "Bronze"),
            ("silver", "Silver"),
            ("gold", "Gold"),
            ("diamond", "Diamond"),
        ],
        default="none",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'  

    def __str__(self):
        return self.user.username