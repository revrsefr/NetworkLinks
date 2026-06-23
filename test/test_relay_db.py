"""
Tests for the relay links database: the JSON tuple/set codec and transparent
migration of a legacy pickle database.
"""
import os
import json
import pickle
import tempfile
import unittest

from pylinkirc.plugins import relay

RelayDataStore = relay.RelayDataStore

# Importing relay instantiates a module-level datastore whose periodic save
# timer is a non-daemon thread; cancel it so the test process can exit.
if relay.datastore.exportdb_timer:
    relay.datastore.exportdb_timer.cancel()


def tearDownModule():
    if relay.datastore.exportdb_timer:
        relay.datastore.exportdb_timer.cancel()


def _sample_store():
    return {
        ('netA', '#chan'): {
            'links': {('netB', '#chan'), ('netC', '#other')},
            'blocked_nets': {'evilnet'},
            'allowed_nets': set(),
            'creator': 'admin',
            'ts': 1700000000.0,
            'use_whitelist': False,
            'claim': ['netA'],
            'modedelta': [['+n', None]],
            'description': 'main channel',
        },
        ('netA', '#empty'): {
            'links': set(),
            'blocked_nets': set(),
            'allowed_nets': {'netB', 'netC'},
            'creator': 'someone',
            'ts': 1700000001.0,
            'use_whitelist': True,
            'claim': [],
        },
    }


class RelayCodecTest(unittest.TestCase):
    def test_encode_is_json_serialisable(self):
        enc = RelayDataStore._encode(_sample_store())
        # Must survive a real json round-trip (no tuples/sets left).
        reparsed = json.loads(json.dumps(enc))
        self.assertEqual(reparsed['version'], relay.RELAY_DB_VERSION)
        self.assertEqual(len(reparsed['channels']), 2)

    def test_roundtrip_preserves_tuples_and_sets(self):
        store = _sample_store()
        decoded = RelayDataStore._decode(RelayDataStore._encode(store))
        self.assertEqual(decoded, store)
        # Spot-check the reconstructed container types.
        entry = decoded[('netA', '#chan')]
        self.assertIsInstance(list(decoded)[0], tuple)
        self.assertIsInstance(entry['links'], set)
        self.assertIn(('netB', '#chan'), entry['links'])
        self.assertIsInstance(entry['allowed_nets'], set)

    def test_decode_tolerates_missing_set_keys(self):
        data = {'version': 1, 'channels': [
            {'network': 'n', 'channel': '#c', 'links': [['n2', '#c']], 'creator': 'x'}
        ]}
        decoded = RelayDataStore._decode(data)
        self.assertEqual(decoded[('n', '#c')]['links'], {('n2', '#c')})


class RelayStoreFileTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._stores = []

    def tearDown(self):
        for s in self._stores:
            if s.exportdb_timer:
                s.exportdb_timer.cancel()

    def _store(self, filename='relay.json'):
        # save_frequency must be > 0 (the implementation treats 0 as "unset");
        # we cancel the resulting timer in tearDown.
        s = RelayDataStore('test-relay', filename, save_frequency=99999,
                            data_dir=self.tmpdir)
        self._stores.append(s)
        return s

    def test_save_then_load(self):
        s1 = self._store()
        s1.store.update(_sample_store())
        s1.save()
        # The on-disk form is plain JSON.
        with open(os.path.join(self.tmpdir, 'relay.json')) as f:
            json.load(f)
        # A fresh store loads the same data back.
        s2 = self._store()
        self.assertEqual(s2.store, _sample_store())

    def test_missing_db_starts_empty(self):
        s = self._store(filename='does-not-exist.json')
        self.assertEqual(s.store, {})

    def test_legacy_pickle_is_migrated(self):
        path = os.path.join(self.tmpdir, 'legacy.db')
        with open(path, 'wb') as f:
            pickle.dump(_sample_store(), f, protocol=4)

        s = self._store(filename='legacy.db')
        # Data is available immediately, with native tuple/set types intact.
        self.assertEqual(s.store, _sample_store())
        # The original pickle is preserved as a backup.
        self.assertTrue(os.path.exists(path + '.pickle.bak'))

        # After a save the file becomes JSON and reloads cleanly.
        s.save()
        with open(path) as f:
            self.assertEqual(json.load(f)['version'], relay.RELAY_DB_VERSION)
        s2 = self._store(filename='legacy.db')
        self.assertEqual(s2.store, _sample_store())


if __name__ == '__main__':
    unittest.main()
