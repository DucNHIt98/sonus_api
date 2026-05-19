from django.db import migrations


_INDEX_SQL = [
    'CREATE INDEX IF NOT EXISTS subscriptions_user_status_period_idx ON subscriptions(user_id, status, current_period_end DESC)',
    'CREATE INDEX IF NOT EXISTS subscriptions_customer_idx ON subscriptions(stripe_customer_id)',
]

_REVERSE_SQL = [
    'DROP INDEX IF EXISTS subscriptions_customer_idx',
    'DROP INDEX IF EXISTS subscriptions_user_status_period_idx',
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
        ('payments', '0002_create_subscriptions_table'),
    ]

    operations = [
        migrations.RunPython(_run_index_sql, _reverse_index_sql, atomic=False),
    ]
