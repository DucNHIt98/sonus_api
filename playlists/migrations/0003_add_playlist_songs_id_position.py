from django.db import migrations


_SQL = [
    'ALTER TABLE playlist_songs ADD COLUMN IF NOT EXISTS id bigserial',
    'ALTER TABLE playlist_songs ADD COLUMN IF NOT EXISTS position integer NOT NULL DEFAULT 0',
    'ALTER TABLE playlist_songs ADD CONSTRAINT playlist_songs_pkey PRIMARY KEY (id)',
    'CREATE INDEX IF NOT EXISTS playlist_songs_playlist_id_idx ON playlist_songs(playlist_id)',
    'CREATE INDEX IF NOT EXISTS playlist_songs_song_id_idx ON playlist_songs(song_id)',
]

_REVERSE_SQL = [
    'DROP INDEX IF EXISTS playlist_songs_song_id_idx',
    'DROP INDEX IF EXISTS playlist_songs_playlist_id_idx',
    'ALTER TABLE playlist_songs DROP CONSTRAINT IF EXISTS playlist_songs_pkey',
    'ALTER TABLE playlist_songs DROP COLUMN IF EXISTS position',
    'ALTER TABLE playlist_songs DROP COLUMN IF EXISTS id',
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
        ('playlists', '0002_playlist_user_playlistsong_added_at'),
    ]

    operations = [
        migrations.RunPython(_run_sql, _reverse_sql, atomic=False),
    ]
