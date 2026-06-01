"""Migrationshilfen für einmalige App-Start-Migrationen."""

from __future__ import annotations

import json

_SETTINGS_COLLECTION = "_settings"
_SCHEDULER_COLLECTION = "scheduler_jobs"

# ── pakete → archlinux ────────────────────────────────────────────────────────

_OLD_MODULE_KEY = "pakete"
_NEW_MODULE_KEY = "archlinux"
_STEP_RENAMES = {
    "pakete.update_all": "archlinux.update_all",
    "pakete.mark_orphans": "archlinux.mark_orphans",
}

# ── docker → builder ──────────────────────────────────────────────────────────

_DOCKER_OLD_KEY = "docker"
_BUILDER_NEW_KEY = "builder"
_BUILDER_STEP_RENAMES = {
    "docker.build_arch_builder": "builder.build_arch_builder",
}


def migrate_archlinux_module_state() -> dict[str, int]:
    """Migriert alte pakete-Daten auf den neuen archlinux-Modul-Key.

    Die Migration ist idempotent:
    - vorhandene archlinux-Einträge haben Vorrang
    - alte pakete-Einträge und Settings werden nach erfolgreicher Übernahme entfernt
    - Scheduler-Job-Schritte werden nur bei Bedarf umgeschrieben
    """
    from astrapi_core.system.db import kv_delete, kv_get, kv_list, kv_set, kv_set_many

    migrated_items = 0
    migrated_settings = 0
    migrated_scheduler_jobs = 0

    old_items = kv_list(_OLD_MODULE_KEY)
    if old_items:
        new_items = kv_list(_NEW_MODULE_KEY)
        merged_items = dict(old_items)
        merged_items.update(new_items)
        kv_set_many(_NEW_MODULE_KEY, merged_items)
        for item_key in old_items:
            kv_delete(_OLD_MODULE_KEY, item_key)
        migrated_items = len(old_items)

    old_prefix = f"module.{_OLD_MODULE_KEY}."
    new_prefix = f"module.{_NEW_MODULE_KEY}."
    for setting_key, raw_value in kv_list(_SETTINGS_COLLECTION).items():
        if not setting_key.startswith(old_prefix):
            continue
        suffix = setting_key[len(old_prefix) :]
        new_key = f"{new_prefix}{suffix}"
        if kv_get(_SETTINGS_COLLECTION, new_key) is None:
            kv_set(_SETTINGS_COLLECTION, new_key, raw_value)
        kv_delete(_SETTINGS_COLLECTION, setting_key)
        migrated_settings += 1

    scheduler_jobs = kv_list(_SCHEDULER_COLLECTION)
    for job_id, raw_job in scheduler_jobs.items():
        try:
            payload = json.loads(raw_job)
        except json.JSONDecodeError:
            continue
        steps = payload.get("steps")
        if not isinstance(steps, list):
            continue
        updated_steps = [_STEP_RENAMES.get(step, step) for step in steps]
        if updated_steps == steps:
            continue
        payload["steps"] = updated_steps
        kv_set(_SCHEDULER_COLLECTION, job_id, json.dumps(payload))
        migrated_scheduler_jobs += 1

    return {
        "items": migrated_items,
        "settings": migrated_settings,
        "scheduler_jobs": migrated_scheduler_jobs,
    }


def migrate_builder_module_state() -> dict[str, int]:
    """Migriert alte docker-Daten auf den neuen builder-Modul-Key.

    Die Migration ist idempotent:
    - vorhandene builder-Einträge haben Vorrang
    - alte docker-Einträge und Settings werden nach erfolgreicher Übernahme entfernt
    - Scheduler-Job-Schritte (docker.build_arch_builder) werden umgeschrieben
    """
    from astrapi_core.system.db import kv_delete, kv_get, kv_list, kv_set, kv_set_many

    migrated_items = 0
    migrated_settings = 0
    migrated_scheduler_jobs = 0

    old_items = kv_list(_DOCKER_OLD_KEY)
    if old_items:
        new_items = kv_list(_BUILDER_NEW_KEY)
        merged_items = dict(old_items)
        merged_items.update(new_items)
        kv_set_many(_BUILDER_NEW_KEY, merged_items)
        for item_key in old_items:
            kv_delete(_DOCKER_OLD_KEY, item_key)
        migrated_items = len(old_items)

    old_prefix = f"module.{_DOCKER_OLD_KEY}."
    new_prefix = f"module.{_BUILDER_NEW_KEY}."
    for setting_key, raw_value in kv_list(_SETTINGS_COLLECTION).items():
        if not setting_key.startswith(old_prefix):
            continue
        suffix = setting_key[len(old_prefix) :]
        new_key = f"{new_prefix}{suffix}"
        if kv_get(_SETTINGS_COLLECTION, new_key) is None:
            kv_set(_SETTINGS_COLLECTION, new_key, raw_value)
        kv_delete(_SETTINGS_COLLECTION, setting_key)
        migrated_settings += 1

    scheduler_jobs = kv_list(_SCHEDULER_COLLECTION)
    for job_id, raw_job in scheduler_jobs.items():
        try:
            payload = json.loads(raw_job)
        except json.JSONDecodeError:
            continue
        steps = payload.get("steps")
        if not isinstance(steps, list):
            continue
        updated_steps = [_BUILDER_STEP_RENAMES.get(step, step) for step in steps]
        if updated_steps == steps:
            continue
        payload["steps"] = updated_steps
        kv_set(_SCHEDULER_COLLECTION, job_id, json.dumps(payload))
        migrated_scheduler_jobs += 1

    return {
        "items": migrated_items,
        "settings": migrated_settings,
        "scheduler_jobs": migrated_scheduler_jobs,
    }
