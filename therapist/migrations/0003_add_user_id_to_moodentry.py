from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("therapist", "0002_alter_moodentry_options_alter_moodentry_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="moodentry",
            name="user_id",
            field=models.CharField(default="legacy", max_length=128, db_index=True),
            preserve_default=False,
        ),
    ]
