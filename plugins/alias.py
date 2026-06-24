# alias.py: defines command aliases from the config.
#
# Example config:
#   aliases:
#       gkill: "masskill --akill"
#       k: "kick"
#
# Calling "gkill <mask>" then runs "masskill --akill <mask>". The target
# command does its own permission check, so aliases inherit those.

from __future__ import annotations

from netlink import conf, utils, world
from netlink.log import log


def _make_alias(target):
    def alias(irc, source, args):
        text = target
        if args:
            text += ' ' + ' '.join(args)
        world.services['netlink'].call_cmd(irc, source, text, called_in=irc.called_in)
    alias.__doc__ = "<args>\n\n    Alias for: %s" % target
    return alias


for _name, _target in (conf.conf.get('aliases') or {}).items():
    utils.add_cmd(_make_alias(_target), name=_name.lower())
    log.debug('alias: bound %r -> %r', _name, _target)
