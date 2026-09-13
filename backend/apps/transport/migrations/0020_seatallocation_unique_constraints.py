"""
Make over-allocation impossible at the database level.

Two students can never hold the same seat on the same bus, and a student can
never hold two seats. The application already checks both, but only the
database can enforce them against concurrent requests and against rows written
by other code paths.

Kept apart from the data repair in 0019 on purpose: that migration deletes
rows, which leaves foreign-key trigger events pending, and Postgres refuses an
ALTER TABLE on a table that still has them ("cannot ALTER TABLE ... because it
has pending trigger events"). A separate migration runs in its own
transaction, after those events have been flushed.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transport", "0019_seatallocation_capacity_integrity"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="seatallocation",
            constraint=models.UniqueConstraint(
                fields=("route_assignment", "seat_number"),
                name="uniq_seat_number_per_assignment",
            ),
        ),
        migrations.AddConstraint(
            model_name="seatallocation",
            constraint=models.UniqueConstraint(
                fields=("registration",),
                name="uniq_seat_per_registration",
            ),
        ),
    ]
