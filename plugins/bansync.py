# bansync.py: synchronizes server bans (G-lines / akills) across linked networks. (#341)
#
# Opt-in per network via servers::<net>::bansync: true, or globally via
# bansync::enabled: true. When a server ban is set or removed on one enabled
# network, it is replayed on the others.

from __future__ import annotations

import time

from netlink import conf, utils, world
from netlink.log import log

# Masks we recently propagated, mapped to an expiry time. Used to suppress the echo
# that comes back from the networks we just set the ban on (otherwise networks would
# bounce the same ban back and forth forever).
_recently_synced: dict = {}
_SUPPRESS_SECONDS = 30


def main(irc=None):
    return None


def die(irc=None):
    _recently_synced.clear()


def _enabled(irc) -> bool:
    """Whether ban sync is enabled for the given network."""
    return bool(irc.serverdata.get('bansync',
                conf.conf.get('bansync', {}).get('enabled', False)))


def _target_source(remoteirc):
    """The UID/SID to attribute synced bans to on the remote network."""
    if remoteirc.pseudoclient:
        return remoteirc.pseudoclient.uid
    return remoteirc.sid


def _propagate(irc, mask, method, *call_args):
    """Replays a ban add/remove (the named protocol method) onto every other enabled,
    connected network, suppressing the echo of bans we ourselves just set."""
    now = time.time()
    for expired in [m for m, exp in _recently_synced.items() if exp < now]:
        del _recently_synced[expired]

    if _recently_synced.get(mask, 0) > now:
        log.debug('(%s) bansync: ignoring echo of %s', irc.name, mask)
        return

    for netname, remoteirc in world.networkobjects.copy().items():
        if netname == irc.name or not remoteirc.connected.is_set() or not _enabled(remoteirc):
            continue
        _recently_synced[mask] = now + _SUPPRESS_SECONDS
        try:
            getattr(remoteirc, method)(_target_source(remoteirc), *call_args)
            log.info('(%s) bansync: replayed %s for %s on %s', irc.name, method, mask, netname)
        except Exception:
            log.exception('(%s) bansync: failed to %s %s on %s', irc.name, method, mask, netname)


def handle_server_ban(irc, source: str, command: str, args: dict):
    """Replays a newly-set server ban onto other networks."""
    if not _enabled(irc) or args.get('type') != 'G':
        return
    _propagate(irc, args['mask'], 'set_server_ban',
               args.get('duration', 0), args['user'], args['host'], args.get('reason', 'Banned'))


def handle_server_unban(irc, source: str, command: str, args: dict):
    """Replays a server ban removal onto other networks."""
    if not _enabled(irc) or args.get('type') != 'G':
        return
    _propagate(irc, args['mask'], 'del_server_ban', args['user'], args['host'])


utils.add_hook(handle_server_ban, 'SERVER_BAN')
utils.add_hook(handle_server_unban, 'SERVER_UNBAN')
