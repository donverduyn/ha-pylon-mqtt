"""Unit tests for stack identity derivation (custom_components.pylontech_mqtt.entity).

Regression coverage for the collision cases a naive topic.replace("/", "_")
identity scheme allowed: two brokers sharing the default topic, and distinct
topics that munge to the same string (see entity.stack_id_from_broker).
"""

from custom_components.pylontech_mqtt.entity import stack_id_from_broker


class TestStackIdFromBroker:
    def test_deterministic(self) -> None:
        """The same inputs must always produce the same identity."""
        a = stack_id_from_broker("localhost", 1883, "pylontech/stack")
        b = stack_id_from_broker("localhost", 1883, "pylontech/stack")
        assert a == b

    def test_different_hosts_do_not_collide(self) -> None:
        """Two brokers both using the default topic must not collide."""
        a = stack_id_from_broker("broker-a.local", 1883, "pylontech/stack")
        b = stack_id_from_broker("broker-b.local", 1883, "pylontech/stack")
        assert a != b

    def test_different_ports_do_not_collide(self) -> None:
        a = stack_id_from_broker("localhost", 1883, "pylontech/stack")
        b = stack_id_from_broker("localhost", 8883, "pylontech/stack")
        assert a != b

    def test_slash_and_underscore_topics_do_not_collide(self) -> None:
        """ "plant/stack" and "plant_stack" must not munge to the same identity
        (a plain "/" -> "_" replace would have collided them)."""
        a = stack_id_from_broker("localhost", 1883, "plant/stack")
        b = stack_id_from_broker("localhost", 1883, "plant_stack")
        assert a != b
