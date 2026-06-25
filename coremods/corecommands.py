"""
corecommands.py - Implements core NetLink commands.
"""

from __future__ import annotations

import sys

from netlink import utils, world
from netlink.log import log

from . import control, permissions

__all__ = []

# Essential, core commands go here so that the "commands" plugin with less-important,
# but still generic functions can be reloaded.

@utils.add_cmd
def shutdown(irc, source: str, args: list):
    """takes no arguments.

    Exits NetLink by disconnecting all networks."""
    permissions.check_permissions(irc, source, ['core.shutdown'])
    log.info('(%s) SHUTDOWN requested by %s, exiting...', irc.name, irc.get_hostmask(source))
    control.shutdown(irc=irc)

@utils.add_cmd
def load(irc, source: str, args: list):
    """<plugin name>.

    Loads a plugin from the plugin folder."""
    # Note: reload capability is acceptable here, because all it actually does is call
    # load after unload.
    permissions.check_permissions(irc, source, ['core.load', 'core.reload'])

    try:
        name = args[0]
    except IndexError:
        irc.reply("Error: Not enough arguments. Needs 1: plugin name.")
        return
    if name in world.plugins:
        irc.reply("Error: %r is already loaded." % name)
        return
    log.info('(%s) Loading plugin %r for %s', irc.name, name, irc.get_hostmask(source))
    try:
        control.load_plugin(name, irc=irc)
    except ImportError as e:
        if str(e) == ('No module named %r' % name):
            log.exception('Failed to load plugin %r: The plugin could not be found.', name)
        else:
            log.exception('Failed to load plugin %r: ImportError.', name)
        raise
    irc.reply("Loaded plugin %r." % name)

@utils.add_cmd
def unload(irc, source: str, args: list):
    """<plugin name>.

    Unloads a currently loaded plugin."""
    permissions.check_permissions(irc, source, ['core.unload', 'core.reload'])

    try:
        name = args[0]
    except IndexError:
        irc.reply("Error: Not enough arguments. Needs 1: plugin name.")
        return

    if name in world.plugins:
        log.info('(%s) Unloading plugin %r for %s', irc.name, name, irc.get_hostmask(source))
        control.unload_plugin(name, irc=irc)
        irc.reply("Unloaded plugin %r." % name)
        return True  # We succeeded, make it clear (this status is used by reload() below)
    else:
        irc.reply("Unknown plugin %r." % name)

@utils.add_cmd
def reload(irc, source: str, args: list):
    """<plugin name>.

    Loads a plugin from the plugin folder."""
    if not args:
        irc.reply("Error: Not enough arguments. Needs 1: plugin name.")
        return

    # Note: these functions do permission checks, so there are none needed here.
    if unload(irc, source, args):
        load(irc, source, args)

@utils.add_cmd
def reloadcore(irc, source: str, args: list):
    """<coremod name>.

    Reloads a core module (one of the modules in coremods/) in place. Unlike
    plugins, coremods are reloaded with importlib.reload so that modules which
    import them keep their references working."""
    permissions.check_permissions(irc, source, ['core.reloadcore'])
    try:
        name = args[0]
    except IndexError:
        irc.error("Not enough arguments. Needs 1: coremod name.")
        return

    modulename = 'netlink.coremods.' + name
    if modulename not in sys.modules:
        irc.error("Unknown or unloaded coremod %r." % name)
        return
    if name in control.UNRELOADABLE_COREMODS:
        irc.error("Coremod %r can't be reloaded at runtime (it holds shared state)." % name)
        return

    log.info('(%s) Reloading coremod %r for %s', irc.name, name, irc.get_hostmask(source))
    try:
        control.reload_coremod(name, irc=irc)
    except Exception as e:
        log.exception('(%s) Failed to reload coremod %r', irc.name, name)
        irc.error("Failed to reload coremod %r: %s: %s" % (name, type(e).__name__, e))
        return
    irc.reply("Reloaded coremod %r." % name)

@utils.add_cmd
def rehash(irc, source: str, args: list):
    """takes no arguments.

    Reloads the configuration file along with all configured plugins and coremods,
    and (dis)connects added/removed networks -- all in place, without dropping the
    links that are still configured."""
    permissions.check_permissions(irc, source, ['core.rehash'])
    try:
        errors = control.rehash()
    except Exception as e:  # Something went wrong loading the config, abort.
        irc.reply("Error loading configuration file: %s: %s" % (type(e).__name__, e))
        return

    irc.announce_administration("%s rehashed the NetLink configuration." % irc.get_hostmask(source))
    if errors:
        irc.reply("Rehash complete with %d error(s): %s" % (len(errors), '; '.join(errors)))
    else:
        irc.reply("Done. Reloaded config, plugins and coremods; links left intact.")

@utils.add_cmd
def clearqueue(irc, source: str, args: list):
    """takes no arguments.

    Clears the outgoing text queue for the current connection."""
    permissions.check_permissions(irc, source, ['core.clearqueue'])
    irc._queue.queue.clear()
