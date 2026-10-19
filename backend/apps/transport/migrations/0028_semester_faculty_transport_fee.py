from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transport', '0027_studentprofile_user_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='semester',
            name='faculty_transport_fee',
            field=models.DecimalField(decimal_places=0, default=9000, max_digits=10),
        ),
    ]
