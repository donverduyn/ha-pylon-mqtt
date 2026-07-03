"""The Pylontech MQTT integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_MQTT_HOST,
    CONF_MQTT_PASS,
    CONF_MQTT_PORT,
    CONF_MQTT_TLS,
    CONF_MQTT_TOPIC,
    CONF_MQTT_USER,
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_TOPIC,
    DOMAIN,
)
from .coordinator import PylontechCoordinator
from .entity import stack_id_from_broker, stack_id_from_topic

PLATFORMS = ["sensor", "number"]

_LOGGER = logging.getLogger(__name__)

# Hidden, non-schema key stashed in entry.data to remember the identity
# token that was actually used to create the current registry entries.
# Preserved across reconfigures (see config_flow.async_step_reconfigure) so
# that a broker/topic change can still be migrated forward instead of
# orphaning the old entities — entry.data is otherwise fully replaced by
# whatever the reconfigure form submitted.
_STACK_ID_KEY = "_stack_id"


def _migrate_registry_identity(
    hass: HomeAssistant, entry: ConfigEntry, host: str, port: int, topic_prefix: str
) -> None:
    """Rename registry entries to the current identity scheme (see
    entity.stack_id_from_broker) from whichever older scheme they were
    created under.

    Entity/device identity has gone through multiple schemes over time:
    entry.entry_id (a fresh random value every config-entry creation, so the
    documented delete-and-recreate upgrade path orphaned everything),
    topic-only hashing (collided when two brokers shared a topic, or when
    "plant/stack" and "plant_stack" both munged to "plant_stack"), and now
    host+port+topic hashing. This runs on every setup; it is a plain
    identifier-prefix rename, so it is a no-op once an entry's registry
    entries already use the current scheme.
    """
    new_stack_id = stack_id_from_broker(host, port, topic_prefix)
    new_prefix = f"{new_stack_id}_"

    old_prefixes = {
        f"{entry.entry_id}_",
        f"{stack_id_from_topic(topic_prefix)}_",
    }
    prior_stack_id = entry.data.get(_STACK_ID_KEY)
    if prior_stack_id:
        old_prefixes.add(f"{prior_stack_id}_")
    old_prefixes.discard(new_prefix)

    if old_prefixes:
        device_reg = dr.async_get(hass)
        for device in list(
            dr.async_entries_for_config_entry(device_reg, entry.entry_id)
        ):
            new_identifiers = set()
            changed = False
            for domain, ident in device.identifiers:
                matched_prefix = next(
                    (p for p in old_prefixes if domain == DOMAIN and ident.startswith(p)),
                    None,
                )
                if matched_prefix:
                    new_identifiers.add(
                        (domain, new_prefix + ident[len(matched_prefix) :])
                    )
                    changed = True
                else:
                    new_identifiers.add((domain, ident))
            if changed:
                device_reg.async_update_device(device.id, new_identifiers=new_identifiers)

        entity_reg = er.async_get(hass)
        for entity in list(
            er.async_entries_for_config_entry(entity_reg, entry.entry_id)
        ):
            if not entity.unique_id:
                continue
            matched_prefix = next(
                (p for p in old_prefixes if entity.unique_id.startswith(p)), None
            )
            if matched_prefix:
                new_unique_id = new_prefix + entity.unique_id[len(matched_prefix) :]
                entity_reg.async_update_entity(entity.entity_id, new_unique_id=new_unique_id)

    if prior_stack_id != new_stack_id:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, _STACK_ID_KEY: new_stack_id}
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Pylontech from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # entry.data is the single source of truth: async_step_user writes the
    # full broker config there on creation, and async_step_reconfigure
    # replaces it wholesale on every update. entry.options is legacy —
    # a now-removed OptionsFlow used to write broker settings there, and
    # preferring it over entry.data meant a stale options copy could keep
    # overriding a successful reconfigure indefinitely. Purge it so nothing
    # (including an old password) lingers in storage after being rotated.
    if entry.options:
        hass.config_entries.async_update_entry(entry, options={})

    # Guard against old serial/TCP config entries that pre-date the MQTT refactor.
    if not entry.data.get(CONF_MQTT_HOST):
        _LOGGER.error(
            "Pylontech config entry is missing MQTT settings. "
            "Please delete and re-add the integration."
        )
        return False

    mqtt_host = entry.data.get(CONF_MQTT_HOST, "")
    mqtt_port = entry.data.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)
    topic_prefix = entry.data.get(CONF_MQTT_TOPIC, DEFAULT_MQTT_TOPIC)
    _migrate_registry_identity(hass, entry, mqtt_host, mqtt_port, topic_prefix)

    coordinator = PylontechCoordinator(
        hass=hass,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_user=entry.data.get(CONF_MQTT_USER, ""),
        mqtt_pass=entry.data.get(CONF_MQTT_PASS, ""),
        topic_prefix=topic_prefix,
        stack_id=stack_id_from_broker(mqtt_host, mqtt_port, topic_prefix),
        mqtt_tls=entry.data.get(CONF_MQTT_TLS, False),
    )

    # connect_async + loop_start are non-blocking; no executor needed.
    coordinator.setup()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # Always remove and shut down the coordinator so the MQTT client thread is
    # never leaked, even when platform unload partially fails.
    coordinator: PylontechCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await hass.async_add_executor_job(coordinator.shutdown)
    return unload_ok
