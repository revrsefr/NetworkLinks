"""
raw.py: Provides a 'raw' command for sending raw text to IRC.
"""

from __future__ import annotations
from netlink import utils
from netlink.coremods import permissions
from netlink.log import log
from netlink import conf

log.warning("The 'raw' plugin is loaded: it lets opers inject arbitrary protocol lines, "
            "which can desync or crash the network. Use with caution; avoid on production.")

@utils.add_cmd
def raw(irc, source: str, args: list):
    """<text>

    Sends raw text to the IRC server.

    Use with caution - This command is only officially supported on Clientbot networks."""
    if not conf.conf['netlink'].get("raw_enabled", False):
        raise RuntimeError("Raw commands are not supported on this protocol")

    # exec.raw is included for backwards compatibility with NetLink 1.x
    permissions.check_permissions(irc, source, ['raw.raw', 'exec.raw'])

    args = ' '.join(args)
    if not args.strip():
        irc.reply('No text entered!')
        return

    # Note: This is loglevel debug so that we don't risk leaking things like
    # NickServ passwords on Clientbot networks.
    log.debug('(%s) Sending raw text %r to IRC for %s', irc.name, args,
              irc.get_hostmask(source))
    irc.send(args)

    irc.reply("Done.")
