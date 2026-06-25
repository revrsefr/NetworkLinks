# ignore.py: lets opers tell NetLink to ignore users -- ignored users are not
# relayed and cannot run NetLink commands. (issue #495)

from __future__ import annotations

from netlink import conf, structures, utils
from netlink.coremods import permissions
from netlink.log import log

# Ignore masks added at runtime via the 'ignore' command, persisted to disk and
# merged with the static config list (ignore::masks).
_dbname = conf.get_database_name('ignore')
datastore = structures.JSONDataStore('ignore', _dbname, default_db={'masks': []})
db = datastore.store


def main(irc=None):
    datastore.load()


def die(irc=None):
    datastore.die()


def _masks():
    """Returns the combined set of runtime and config ignore masks."""
    return set(db.get('masks', [])) | set(conf.conf.get('ignore', {}).get('masks', []))


def is_ignored(irc, uid) -> bool:
    """Returns whether the given user matches any configured ignore mask.

    Other modules (the command dispatcher, relay) consult this when the plugin is
    loaded; internal NetLink clients are never ignored."""
    if uid not in irc.users or irc.is_internal_client(uid):
        return False
    return any(irc.match_host(mask, uid) for mask in _masks())


@utils.add_cmd
def ignore(irc, source: str, args: list):
    """<add|del|list> [<mask>]

    Manages NetLink's ignore list. An ignored user -- matched by a nick!user@host
    mask or an exttarget such as $account:spammer -- is not relayed and cannot run
    NetLink commands. Masks can also be set statically under the config 'ignore' block."""
    permissions.check_permissions(irc, source, ['ignore.manage'])
    masks = db.setdefault('masks', [])
    sub = args[0].lower() if args else 'list'

    if sub in ('list', 'ls'):
        irc.reply("Ignored masks: %s" % (', '.join(sorted(_masks())) or "(none)"))
        return

    mask = ' '.join(args[1:]).strip()
    if not mask:
        irc.error("Not enough arguments. Needs: ignore %s <mask>" % sub)
        return

    if sub == 'add':
        if mask not in masks:
            masks.append(mask)
            datastore.save()
            log.info("(%s) %s added %r to the ignore list", irc.name, irc.get_hostmask(source), mask)
        irc.reply("Done.")
    elif sub in ('del', 'rm', 'remove'):
        if mask in masks:
            masks.remove(mask)
            datastore.save()
            log.info("(%s) %s removed %r from the ignore list", irc.name, irc.get_hostmask(source), mask)
        irc.reply("Done.")
    else:
        irc.error("Unknown subcommand %r. Use add, del, or list." % sub)
