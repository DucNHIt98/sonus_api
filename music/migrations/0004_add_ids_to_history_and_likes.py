from django.db import migrations


_SQL = [
    'ALTER TABLE play_history ADD COLUMN IF NOT EXISTS id bigserial',
    'ALTER TABLE play_history ADD CONSTRAINT play_history_pkey PRIMARY KEY (id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS play_history_user_song_uidx ON play_history(user_id, song_id)',
    'ALTER TABLE liked_songs ADD COLUMN IF NOT EXISTS id bigserial',
    'ALTER TABLE liked_songs ADD CONSTRAINT liked_songs_pkey PRIMARY KEY (id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS liked_songs_user_song_uidx ON liked_songs(user_id, song_id)',
]

_REVERSE_SQL = [
    'DROP INDEX IF EXISTS liked_songs_user_song_uidx',
    'ALTER TABLE liked_songs DROP CONSTRAINT IF EXISTS liked_songs_pkey',
    'ALTER TABLE liked_songs DROP COLUMN IF EXISTS id',
    'DROP INDEX IF EXISTS play_history_user_song_uidx',
    'ALTER TABLE play_history DROP CONSTRAINT IF EXISTS play_history_pkey',
    'ALTER TABLE play_history DROP COLUMN IF EXISTS id',
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
        ('music', '0003_lyric_downloadedsong'),
    ]

    operations = [
        migrations.RunPython(_run_sql, _reverse_sql, atomic=False),
    ]
