# Generated by Django 2.2.8 on 2019-12-10 00:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tom_observations', '0004_observationgroup'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='observationgroup',
            options={'ordering': ('-created',)},
        ),
    ]
