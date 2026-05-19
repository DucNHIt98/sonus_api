from django.db import migrations


_SQL = [
    'CREATE INDEX IF NOT EXISTS songs_title_trgm_idx ON songs USING gin (title gin_trgm_ops)',
    'CREATE INDEX IF NOT EXISTS songs_subtitle_trgm_idx ON songs USING gin (subtitle gin_trgm_ops)',
    'CREATE INDEX IF NOT EXISTS songs_album_name_trgm_idx ON songs USING gin (album_name gin_trgm_ops)',
    'CREATE INDEX IF NOT EXISTS songs_created_at_idx ON songs(created_at DESC)',
]

_REVERSE_SQL = [
    'DROP INDEX IF EXISTS songs_created_at_idx',
    'DROP INDEX IF EXISTS songs_album_name_trgm_idx',
    'DROP INDEX IF EXISTS songs_subtitle_trgm_idx',
    'DROP INDEX IF EXISTS songs_title_trgm_idx',
]


def _run_sql(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for sql in _SQL:
            try:
                cursor.execute(sql)
            except Exception:
                pass


def _reverse_sql(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for sql in _REVERSE_SQL:
            try:
                cursor.execute(sql)
            except Exception:
                pass


class Migration(migrations.Migration):
    dependencies = [
        ('music', '0004_add_ids_to_history_and_likes'),
    ]

    operations = [
        migrations.RunPython(_run_sql, _reverse_sql, atomic=False),
    ]
