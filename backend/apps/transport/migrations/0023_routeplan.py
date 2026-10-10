import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def seed_current_plan(apps, schema_editor):
    """Existing installs start with one active plan standing for today's routes."""
    RoutePlan = apps.get_model("transport", "RoutePlan")
    if not RoutePlan.objects.exists():
        RoutePlan.objects.create(name="Current routes", is_active=True, activated_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ('transport', '0022_driver_user'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RoutePlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('data', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=False)),
                ('activated_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-is_active', 'name'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('is_active',), name='one_active_route_plan')],
            },
        ),
        migrations.RunPython(seed_current_plan, migrations.RunPython.noop),
    ]
