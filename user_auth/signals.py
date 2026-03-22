from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Badge, UserProfile


@receiver(post_save, sender=UserProfile)
def assign_default_bronze_badge(sender, instance, created, **kwargs):
    """New profiles start at Bronze with the Bronze badge attached (for display / gamification)."""
    if not created:
        return
    bronze = Badge.objects.filter(name__iexact="bronze").first()
    if bronze:
        instance.badges.add(bronze)
    if instance.badge_level == "none":
        UserProfile.objects.filter(pk=instance.pk).update(badge_level="bronze")
