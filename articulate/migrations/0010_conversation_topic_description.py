# Generated manually for topic context on AI opening

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("articulate", "0009_topicprogress_last_score"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="topic_description",
            field=models.TextField(
                blank=True,
                help_text="Optional context from the topic card or daily topic; used for AI opening.",
            ),
        ),
    ]
