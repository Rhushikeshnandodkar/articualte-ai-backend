from django.db import migrations, models


def create_day_pass_plan(apps, schema_editor):
    """Create the ₹15 Day Pass plan if it doesn't exist yet (idempotent)."""
    SubscriptionPlan = apps.get_model('user_auth', 'SubscriptionPlan')
    if SubscriptionPlan.objects.filter(plan_type='day_pass').exists():
        return
    SubscriptionPlan.objects.create(
        name='Day Pass',
        description=(
            '<ul>'
            '<li><strong>Full access for one day</strong> — practice as much as you want</li>'
            '<li>All table topics unlocked</li>'
            '<li>AI voice practice with real-time feedback</li>'
            '<li>Valid until midnight on the day you buy</li>'
            '</ul>'
        ),
        price=15,
        duration=1,
        limit_minutes=1440,
        plan_type='day_pass',
    )


def remove_day_pass_plan(apps, schema_editor):
    SubscriptionPlan = apps.get_model('user_auth', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(plan_type='day_pass').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user_auth', '0011_default_bronze_badge'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='plan_type',
            field=models.CharField(
                choices=[('monthly', 'Monthly'), ('day_pass', 'Day Pass')],
                default='monthly',
                help_text='Day passes are valid only for the calendar day they are purchased.',
                max_length=20,
            ),
        ),
        migrations.RunPython(create_day_pass_plan, remove_day_pass_plan),
    ]
