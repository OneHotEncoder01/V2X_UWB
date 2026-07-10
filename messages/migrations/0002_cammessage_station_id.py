from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messages", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="cammessage",
            name="station_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
    ]
