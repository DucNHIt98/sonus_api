from django.db import migrations


_SQL = [
    '''CREATE TABLE IF NOT EXISTS subscriptions (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        stripe_subscription_id text UNIQUE,
        stripe_customer_id text,
        status text NOT NULL DEFAULT 'incomplete',
        current_period_start timestamptz,
        current_period_end timestamptz,
        cancel_at_period_end boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )''',
    'CREATE INDEX IF NOT EXISTS subscriptions_user_id_idx ON subscriptions(user_id)',
    'CREATE INDEX IF NOT EXISTS subscriptions_status_idx ON subscriptions(status)',
]

_REVERSE_SQL = [
    'DROP TABLE IF EXISTS subscriptions',
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
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(_run_sql, _reverse_sql, atomic=False),
    ]
