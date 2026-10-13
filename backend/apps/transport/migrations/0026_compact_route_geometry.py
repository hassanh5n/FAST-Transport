from django.db import migrations


def compact_saved_lines(apps, schema_editor):
    """Shrink road lines saved before compaction, so map loads read less from the database."""
    from apps.transport.views.maps import _compact_line

    Route = apps.get_model("transport", "Route")
    for route in Route.objects.exclude(geometry=None).only("id", "geometry"):
        compact = _compact_line(route.geometry)
        if compact != route.geometry:
            Route.objects.filter(pk=route.pk).update(geometry=compact)


class Migration(migrations.Migration):
    dependencies = [("transport", "0025_stop_is_campus")]
    operations = [migrations.RunPython(compact_saved_lines, migrations.RunPython.noop)]
