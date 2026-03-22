# Daily topic completion + past titles for LLM de-duplication

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user_auth", "0009_paymentorder"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="daily_topic_completed_today",
            field=models.BooleanField(
                default=False,
                help_text="True after user ends a session whose topic matched today's daily topic; allows a fresh daily topic the same day.",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="daily_topic_past_titles",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Recent daily topic titles so the LLM avoids repeats.",
            ),
        ),
    ]
