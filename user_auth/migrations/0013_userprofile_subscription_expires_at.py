from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_auth', '0012_subscriptionplan_plan_type_day_pass'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subscription_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
