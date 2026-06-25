"""
corecommands.py - Implements core NetLink commands.
"""

from __future__ import annotations

import gc
import importlib
import sys

from netlink import utils, world
from netlink.log import log

from . import control, permissions

__all__ = []


def _remove_module_commands_hooks(modulename):
    """Removes all commands and hooks registered by the given module name."""
    cmds = world.services['netlink'].commands
    for cmdname, cmdfuncs in cmds.copy().items():
        for cmdfunc in cmdfuncs.copy():
            if cmdfunc.__module__ == modulename:
                cmds[cmdname].remove(cmdfunc)
        if not cmds[cmdname]:
            del cmds[cmdname]

    for hookname, hookpairs in world.hooks.copy().items():
        for hookpair in hookpairs.copy():
            if hookpair[1].__module__ == modulename:
                world.hooks[hookname].remove(hookpair)
        if not world.hooks[hookname]:
            del world.hooks[hookname]

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
        world.plugins[name] = pl = utils._load_plugin(name)
    except ImportError as e:
        if str(e) == ('No module named %r' % name):
            log.exception('Failed to load plugin %r: The plugin could not be found.', name)
        else:
            log.exception('Failed to load plugin %r: ImportError.', name)
        raise
    else:
        if hasattr(pl, 'main'):
            log.debug('Calling main() function of plugin %r', pl)
            pl.main(irc=irc)
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

    # Since we're using absolute imports in 0.9.x+, the module name differs from the actual plugin
    # name.
    modulename = utils.PLUGIN_PREFIX + name

    if name in world.plugins:
        log.info('(%s) Unloading plugin %r for %s', irc.name, name, irc.get_hostmask(source))
        pl = world.plugins[name]
        log.debug('sys.getrefcount of plugin %s is %s', pl, sys.getrefcount(pl))

        # Remove any command functions defined by the plugin.
        for cmdname, cmdfuncs in world.services['netlink'].commands.copy().items():
            log.debug('cmdname=%s, cmdfuncs=%s', cmdname, cmdfuncs)

            for cmdfunc in cmdfuncs:
                log.debug('__module__ of cmdfunc %s is %s', cmdfunc, cmdfunc.__module__)
                if cmdfunc.__module__ == modulename:
                    log.debug("Removing %s from world.services['netlink'].commands[%s]", cmdfunc, cmdname)
                    world.services['netlink'].commands[cmdname].remove(cmdfunc)

                    # If the cmdfunc list is empty, remove it.
                    if not cmdfuncs:
                        log.debug("Removing world.services['netlink'].commands[%s] (it's empty now)", cmdname)
                        del world.services['netlink'].commands[cmdname]

        # Remove any command hooks set by the plugin.
        for hookname, hookpairs in world.hooks.copy().items():
            for hookpair in hookpairs:
                hookfunc = hookpair[1]
                if hookfunc.__module__ == modulename:
                    log.debug('Trying to remove hook func %s (%s) from plugin %s', hookfunc, hookname, modulename)
                    world.hooks[hookname].remove(hookpair)
                    # If the hookfuncs list is empty, remove it.
                    if not hookpairs:
                        del world.hooks[hookname]

        # Call the die() function in the plugin, if present.
        if hasattr(pl, 'die'):
            try:
                pl.die(irc=irc)
            except:  # But don't allow it to crash the server.
                log.exception('(%s) Error occurred in die() of plugin %s, skipping...', irc.name, pl)

        # Delete it from memory (hopefully).
        del world.plugins[name]
        for n in (name, modulename):
            if n in sys.modules:
                del sys.modules[n]
            if n in globals():
                del globals()[n]

        # Garbage collect.
        gc.collect()

        irc.reply("Unloaded plugin %r." % name)
        return True  # We succeeded, make it clear (this status is used by reload() below)
    else:
        irc.reply("Unknown plugin %r." % name)

@utils.add_cmd
def reload(irc, source: str, args: list):
    """<plugin name>.

    Loads a plugin from the plugin folder."""
    try:
        name = args[0]
    except IndexError:
        irc.reply("Error: Not enough arguments. Needs 1: plugin name.")
        return

    # Note: these functions do permission checks, so there are none needed here.
    if unload(irc, source, args):
        load(irc, source, args)

# Coremods that hold accumulated state populated by other modules, so reloading
# them in place would wipe it (permissions: the default_permissions registry).
_UNRELOADABLE_COREMODS = {'permissions'}

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
    if name in _UNRELOADABLE_COREMODS:
        irc.error("Coremod %r can't be reloaded at runtime (it holds shared state)." % name)
        return

    module = sys.modules[modulename]
    log.info('(%s) Reloading coremod %r for %s', irc.name, name, irc.get_hostmask(source))
    _remove_module_commands_hooks(modulename)
    try:
        importlib.reload(module)
    except Exception as e:
        log.exception('(%s) Failed to reload coremod %r', irc.name, name)
        irc.error("Failed to reload coremod %r: %s: %s" % (name, type(e).__name__, e))
        return
    if hasattr(module, 'main'):
        module.main(irc=irc)
    irc.reply("Reloaded coremod %r." % name)

@utils.add_cmd
def rehash(irc, source: str, args: list):
    """takes no arguments.

    Reloads the configuration file for NetLink, (dis)connecting added/removed networks.

    Note: plugins must be manually reloaded."""
    permissions.check_permissions(irc, source, ['core.rehash'])
    try:
        control.rehash()
    except Exception as e:  # Something went wrong, abort.
        irc.reply("Error loading configuration file: %s: %s" % (type(e).__name__, e))
        return
    else:
        irc.announce_administration("%s rehashed the NetLink configuration." % irc.get_hostmask(source))
        irc.reply("Done.")

@utils.add_cmd
def clearqueue(irc, source: str, args: list):
    """takes no arguments.

    Clears the outgoing text queue for the current connection."""
    permissions.check_permissions(irc, source, ['core.clearqueue'])
    irc._queue.queue.clear()
