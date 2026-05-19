from django.db import migrations


_INDEX_SQL = [
    'CREATE INDEX IF NOT EXISTS play_history_user_last_played_idx ON play_history(user_id, last_played DESC)',
    'CREATE INDEX IF NOT EXISTS play_history_user_count_idx ON play_history(user_id, count DESC)',
    'CREATE INDEX IF NOT EXISTS liked_songs_user_liked_at_idx ON liked_songs(user_id, liked_at DESC)',
    'CREATE INDEX IF NOT EXISTS downloaded_songs_user_downloaded_at_idx ON downloaded_songs(user_id, downloaded_at DESC)',
    'CREATE INDEX IF NOT EXISTS songs_genre_created_at_idx ON songs(genre, created_at DESC)',
    'CREATE INDEX IF NOT EXISTS songs_region_created_at_idx ON songs(region, created_at DESC)',
]

_REVERSE_SQL = [
    'DROP INDEX IF EXISTS songs_region_created_at_idx',
    'DROP INDEX IF EXISTS songs_genre_created_at_idx',
    'DROP INDEX IF EXISTS downloaded_songs_user_downloaded_at_idx',
    'DROP INDEX IF EXISTS liked_songs_user_liked_at_idx',
    'DROP INDEX IF EXISTS play_history_user_count_idx',
    'DROP INDEX IF EXISTS play_history_user_last_played_idx',
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
        ('music', '0005_add_song_search_indexes'),
    ]

    operations = [
        migrations.RunPython(_run_index_sql, _reverse_index_sql, atomic=False),
    ]
