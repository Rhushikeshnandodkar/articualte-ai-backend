from django.db import migrations, models


def upgrade_none_to_bronze(apps, schema_editor):
    UserProfile = apps.get_model("user_auth", "UserProfile")
    Badge = apps.get_model("user_auth", "Badge")
    bronze = Badge.objects.filter(name__iexact="bronze").first()
    if not bronze:
        UserProfile.objects.filter(badge_level="none").update(badge_level="bronze")
        return
    Through = UserProfile.badges.through
    for p in UserProfile.objects.filter(badge_level="none"):
        UserProfile.objects.filter(pk=p.pk).update(badge_level="bronze")
        Through.objects.get_or_create(userprofile_id=p.pk, badge_id=bronze.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("user_auth", "0010_userprofile_daily_topic_rotation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="badge_level",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("bronze", "Bronze"),
                    ("silver", "Silver"),
                    ("gold", "Gold"),
                    ("diamond", "Diamond"),
                ],
                default="bronze",
                max_length=20,
            ),
        ),
        migrations.RunPython(upgrade_none_to_bronze, migrations.RunPython.noop),
    ]
