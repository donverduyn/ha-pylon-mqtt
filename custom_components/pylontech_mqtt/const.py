"""Constants for the Pylontech integration."""

DOMAIN = "pylontech_mqtt"

# MQTT configuration keys
CONF_MQTT_HOST = "mqtt_host"
CONF_MQTT_PORT = "mqtt_port"
CONF_MQTT_USER = "mqtt_user"
CONF_MQTT_PASS = "mqtt_pass"
CONF_MQTT_TOPIC = "mqtt_topic"

DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_TOPIC = "pylontech/stack"

DEFAULT_BATTERY_CAPACITY = 2.4  # kWh — US2000 fallback when spec cannot be parsed
