"""Shared pytest setup for the NetLink test suite.

Disable the periodic datastore autosave before any plugin/datastore is imported.
Otherwise DataStore.__init__ starts a non-daemon threading.Timer (default 300s),
which keeps the interpreter alive and makes pytest hang at exit. Explicit save()
calls still work; only the background timer is suppressed.
"""
from netlink import conf

conf.conf['netlink']['save_delay'] = 0
