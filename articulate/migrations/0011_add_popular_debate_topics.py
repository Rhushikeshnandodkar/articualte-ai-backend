"""Add 20 popular, debate-style table topics (things people love to argue about).

Each prompt asks the speaker to take a side and back it up, which is good table-topics practice.
Idempotent: topics whose title already exists are skipped, and reversing removes only these titles.
"""
from django.db import migrations

TOPICS = [
    # (title, category, level, time_limit_seconds, description)
    ("Is social media doing more harm than good?", "Hot takes", "beginner", 120,
     "Pick a side. Give two reasons and one example from your own life or someone you know."),
    ("Your most unpopular opinion", "Hot takes", "intermediate", 180,
     "Share an opinion most people disagree with. Explain why you believe it and answer one objection."),
    ("Pineapple on pizza: genius or crime?", "Hot takes", "beginner", 120,
     "Defend your food hot take like a lawyer. Be funny, but give real reasons."),
    ("Should phones be banned in schools?", "Hot takes", "beginner", 120,
     "Argue for or against a full ban. Think about students, teachers and parents."),
    ("Is a college degree still worth it?", "Hot takes", "intermediate", 180,
     "Compare a degree with skills, internships or starting work early. Where do you stand, and why?"),

    ("Job or startup at 22: which would you choose?", "Career & money", "intermediate", 180,
     "Choose one path for your first five years. Talk about risk, learning and money."),
    ("Is hustle culture inspiring or toxic?", "Career & money", "intermediate", 180,
     "Is working nights and weekends the way to win, or a road to burnout? Take a clear position."),
    ("Higher salary at a job you hate, or less money at a job you love?", "Career & money", "beginner", 120,
     "Make your choice and explain what would change your mind."),
    ("Work from home or office: which makes people better?", "Career & money", "beginner", 120,
     "Think about focus, friendships, growth and health. Which wins for you?"),
    ("Is it okay to quit a job without another offer?", "Career & money", "intermediate", 180,
     "When is it brave and when is it reckless? Give an example."),

    ("Love marriage or arranged marriage?", "Relationships", "intermediate", 180,
     "Which leads to happier lives today? Be respectful of both sides and give clear reasons."),
    ("Are dating apps ruining real connection?", "Relationships", "intermediate", 180,
     "Do apps help people meet or make relationships shallow? Share what you have seen."),
    ("Should parents decide your career?", "Relationships", "beginner", 120,
     "How much say should family have in what you study or do? Tell a short story if you can."),
    ("Can you stay friends with an ex?", "Relationships", "beginner", 120,
     "Is it mature or a bad idea? Explain your view with a simple example."),

    ("Will AI take your job in the next 10 years?", "Tech & society", "intermediate", 180,
     "Which jobs are safe and which are not? What are you doing to stay ahead?"),
    ("Should AI-generated art count as real art?", "Tech & society", "advanced", 180,
     "Who is the artist: the person, the AI, or the people it learned from? Build an argument."),
    ("Would you let a self-driving car drive your family?", "Tech & society", "intermediate", 180,
     "Talk about trust, safety and who is responsible when something goes wrong."),

    ("Cricket or football: which deserves more fans?", "Life & culture", "beginner", 120,
     "Make the case for your sport with passion and at least two solid reasons."),
    ("Can money buy happiness?", "Life & culture", "advanced", 180,
     "Where does money stop helping? Use examples and give a nuanced answer."),
    ("If you could change one rule in your city, what would it be?", "Life & culture", "advanced", 180,
     "Pick one rule, explain the problem it solves and answer the biggest objection."),
]


def add_topics(apps, schema_editor):
    Topic = apps.get_model("articulate", "Topic")
    existing = set(Topic.objects.values_list("title", flat=True))
    for title, category, level, seconds, description in TOPICS:
        if title in existing:
            continue
        Topic.objects.create(
            title=title,
            category=category,
            level=level,
            time_limit_seconds=seconds,
            description=description,
            is_active=True,
        )


def remove_topics(apps, schema_editor):
    Topic = apps.get_model("articulate", "Topic")
    Topic.objects.filter(title__in=[t[0] for t in TOPICS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("articulate", "0010_conversation_topic_description"),
    ]

    operations = [
        migrations.RunPython(add_topics, remove_topics),
    ]
