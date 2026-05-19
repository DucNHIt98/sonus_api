from django.db import migrations


_INDEX_SQL = [
    'CREATE INDEX IF NOT EXISTS playlists_user_created_at_idx ON playlists(user_id, created_at DESC)',
    'CREATE INDEX IF NOT EXISTS playlist_songs_playlist_position_idx ON playlist_songs(playlist_id, position)',
]

_REVERSE_SQL = [
    'DROP INDEX IF EXISTS playlist_songs_playlist_position_idx',
    'DROP INDEX IF EXISTS playlists_user_created_at_idx',
]


def _run_index_sql(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for sql in _INDEX_SQL:
            try:
                cursor.execute(sql)
            except Exception:
                pass


def _reverse_index_sql(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        for sql in _REVERSE_SQL:
            try:
                cursor.execute(sql)
            except Exception:
                pass


class Migration(migrations.Migration):
    dependencies = [
        ('playlists', '0003_add_playlist_songs_id_position'),
    ]

    operations = [
        migrations.RunPython(_run_index_sql, _reverse_index_sql, atomic=False),
    ]
