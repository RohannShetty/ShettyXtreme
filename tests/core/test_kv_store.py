"""Integration tests for KVStore."""

import pytest

class TestKVStoreBasic:
    def test_put_and_get(self, kv_store):
        kv_store.put("mode", "paper")
        assert kv_store.get("mode") == "paper"

    def test_get_default(self, kv_store):
        assert kv_store.get("nonexistent") is None
        assert kv_store.get("nonexistent", "fallback") == "fallback"

    def test_put_overwrites(self, kv_store):
        kv_store.put("key", "value1")
        kv_store.put("key", "value2")
        assert kv_store.get("key") == "value2"

    def test_delete_removes_key(self, kv_store):
        kv_store.put("temp", "data")
        kv_store.delete("temp")
        assert kv_store.get("temp") is None

    def test_delete_nonexistent_no_error(self, kv_store):
        kv_store.delete("i_dont_exist")

    def test_complex_values(self, kv_store):
        kv_store.put("dict_val", {"a": 1, "b": [2, 3]})
        kv_store.put("list_val", [1, "two", 3.0])
        kv_store.put("int_val", 42)
        kv_store.put("bool_val", False)

        assert kv_store.get("dict_val") == {"a": 1, "b": [2, 3]}
        assert kv_store.get("list_val") == [1, "two", 3.0]
        assert kv_store.get("int_val") == 42
        assert kv_store.get("bool_val") is False


class TestKVStoreKeys:
    def test_keys_no_prefix(self, kv_store):
        kv_store.put("a", 1)
        kv_store.put("b", 2)
        kv_store.put("c", 3)
        all_keys = kv_store.keys()
        assert set(all_keys) == {"a", "b", "c"}

    def test_keys_with_prefix(self, kv_store):
        kv_store.put("sensor.temp", 25)
        kv_store.put("sensor.humidity", 60)
        kv_store.put("config.dry_run", True)
        sensor_keys = kv_store.keys("sensor")
        assert set(sensor_keys) == {"sensor.temp", "sensor.humidity"}

    def test_keys_empty_when_no_match(self, kv_store):
        kv_store.put("abc", 1)
        assert kv_store.keys("xyz") == []

    def test_keys_empty_store(self, kv_store):
        assert kv_store.keys() == []


class TestKVStorePersistence:
    def test_persistence_across_instances(self, tmp_data_dir):
        from shettyxtreme.core.storage import KVStore
        db_path = f"{tmp_data_dir}/persist_test.db"

        store1 = KVStore(db_path)
        store1.put("persistent_key", "persistent_value")
        store1.put("number", 99)
        store1.close()

        store2 = KVStore(db_path)
        assert store2.get("persistent_key") == "persistent_value"
        assert store2.get("number") == 99
        store2.close()

    def test_close_and_reopen(self, kv_store):
        kv_store.put("stay", "alive")
        path = kv_store._conn.execute("PRAGMA database_list").fetchone()[2]
        kv_store.close()

        from shettyxtreme.core.storage import KVStore
        store2 = KVStore(path)
        assert store2.get("stay") == "alive"
        store2.close()
