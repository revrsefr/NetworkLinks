# servprotect.py: Protects against KILL and nick collision floods

from __future__ import annotations

import threading

from netlink import conf, utils
from netlink.log import log

try:
    from cachetools import TTLCache
except ImportError:
    log.warning('servprotect: expiringdict support is deprecated as of NetLink 3.0; consider installing cachetools instead')
    from expiringdict import ExpiringDict as TTLCache

# check for definitions
servprotect_conf = conf.conf.get('servprotect', {})
length = servprotect_conf.get('length', 10)
# 'age' is the time window before the counters reset; accept a duration string.
age = utils.parse_duration(servprotect_conf.get('age', 10))

def _new_cache_dict():
    return TTLCache(length, age)

savecache = _new_cache_dict()
killcache = _new_cache_dict()
lock = threading.Lock()

def handle_kill(irc, numeric: str, command: str, args: dict):
    """
    Tracks kills against NetLink clients. If too many are received,
    automatically disconnects from the network.
    """

    if (args['userdata'] and irc.is_internal_server(args['userdata'].server)) or irc.is_internal_client(args['target']):
        with lock:
            if killcache.setdefault(irc.name, 1) >= length:
                log.error('(%s) servprotect: Too many kills received, aborting!', irc.name)
                irc.disconnect()

            log.debug('(%s) servprotect: Incrementing killcache by 1', irc.name)
            killcache[irc.name] += 1

utils.add_hook(handle_kill, 'KILL')

def handle_save(irc, numeric: str, command: str, args: dict):
    """
    Tracks SAVEs (nick collision) against NetLink clients. If too many are received,
    automatically disconnects from the network.
    """
    if irc.is_internal_client(args['target']):
        with lock:
            if savecache.setdefault(irc.name, 0) >= length:
                log.error('(%s) servprotect: Too many nick collisions, aborting!', irc.name)
                irc.disconnect()

            log.debug('(%s) servprotect: Incrementing savecache by 1', irc.name)
            savecache[irc.name] += 1

utils.add_hook(handle_save, 'SAVE')
