"""
control.py - Implements SHUTDOWN and REHASH functionality.
"""

from __future__ import annotations
import atexit
import gc
import importlib
import os
import signal
import sys
import threading

from netlink import conf, utils, world  # Do not import classes, it'll import loop
from netlink.log import _get_console_log_level, _make_file_logger, _stop_file_loggers, log

from . import login

__all__ = [
    'UNRELOADABLE_COREMODS',
    'load_plugin',
    'rehash',
    'reload_coremod',
    'remove_network',
    'shutdown',
    'unload_plugin',
]

# Coremods that can't be reloaded in place during a rehash:
#  - permissions holds the default_permissions registry populated by other modules
#    (reloading would wipe it),
#  - service_support calls register_service('netlink') at import (reloading raises
#    "already bound"),
#  - control is the module rehash() itself runs from.
UNRELOADABLE_COREMODS = {'permissions', 'service_support', 'control'}


def remove_network(ircobj) -> None:
    """Removes a network object from the pool."""
    # Disable autoconnect first by setting the delay negative.
    ircobj.serverdata['autoconnect'] = -1
    ircobj.disconnect()
    del world.networkobjects[ircobj.name]

def _print_remaining_threads() -> None:
    log.debug('shutdown(): Remaining threads: %s', ['%s/%s' % (t.name, t.ident) for t in threading.enumerate()])

def _remove_pid() -> None:
    pidfile = "%s.pid" % conf.confname
    if world._should_remove_pid:
        # Remove our pid file.
        log.info("Removing PID file %r.", pidfile)
        try:
            os.remove(pidfile)
        except OSError:
            log.exception("Failed to remove PID file %r, ignoring..." % pidfile)
    else:
        log.debug('Not removing PID file %s as world._should_remove_pid is False.' % pidfile)

def _kill_plugins(irc=None) -> None:
    if not world.plugins:
        # No plugins were loaded or we were in a pre-initialized state, ignore.
        return

    log.info("Shutting down plugins.")
    for name, plugin in world.plugins.items():
        # Before closing connections, tell all plugins to shutdown cleanly first.
        if hasattr(plugin, 'die'):
            log.debug('coremods.control: Running die() on plugin %s due to shutdown.', name)
            try:
                plugin.die(irc=irc)
            except:  # But don't allow it to crash the server.
                log.exception('coremods.control: Error occurred in die() of plugin %s, skipping...', name)

# We use atexit to register certain functions so that when NetLink cleans up after itself if it
# shuts down because all networks have been disconnected.
atexit.register(_remove_pid)
atexit.register(_kill_plugins)

def shutdown(irc=None) -> None:
    """Shuts down the NetLink daemon."""
    if world.shutting_down.is_set():  # We froze on shutdown last time, so immediately abort.
        _print_remaining_threads()
        raise KeyboardInterrupt("Forcing shutdown.")

    world.shutting_down.set()

    # HACK: run the _kill_plugins trigger with the current IRC object. XXX: We should really consider removing this
    # argument, since no plugins actually use it to do anything.
    atexit.unregister(_kill_plugins)
    _kill_plugins(irc=irc)

    # Remove our main NetLink bot as well.
    utils.unregister_service('netlink')

    for ircobj in world.networkobjects.copy().values():
        # Disconnect all our networks.
        try:
            remove_network(ircobj)
        except NotImplementedError:
            continue

    log.info("Waiting for remaining threads to stop; this may take a few seconds. If NetLink freezes "
             "at this stage, press Ctrl-C to force a shutdown.")
    _print_remaining_threads()

    # Done.

def _sigterm_handler(signo: int, stack_frame) -> None:
    """Handles SIGTERM and SIGINT gracefully by shutting down the NetLink daemon."""
    log.info("Shutting down on signal %s." % signo)
    shutdown()

signal.signal(signal.SIGTERM, _sigterm_handler)
signal.signal(signal.SIGINT, _sigterm_handler)

def _teardown_module(modulename: str) -> None:
    """Strips every command and hook the named module registered, across ALL service
    bots (not just the main one), so the module can be reloaded without leaving stale
    bindings or duplicating commands that bots register at module load."""
    for sbot in world.services.values():
        for cmdname, cmdfuncs in sbot.commands.copy().items():
            kept = [f for f in cmdfuncs if f.__module__ != modulename]
            if kept:
                sbot.commands[cmdname] = kept
            else:
                del sbot.commands[cmdname]
                sbot.featured_cmds.discard(cmdname)
        # Drop alias entries left dangling once their command is gone.
        for alias, primary in list(sbot.alias_cmds.items()):
            if alias not in sbot.commands or primary not in sbot.commands:
                del sbot.alias_cmds[alias]

    for hookname, hookpairs in world.hooks.copy().items():
        kept = [hp for hp in hookpairs if hp[1].__module__ != modulename]
        if kept:
            world.hooks[hookname] = kept
        else:
            del world.hooks[hookname]

def unload_plugin(name: str, irc=None) -> bool:
    """Unloads a plugin: runs its die(), strips its commands/hooks, drops it from
    memory (so a following load reimports fresh code). Returns True if it was loaded."""
    if name not in world.plugins:
        return False
    modulename = utils.PLUGIN_PREFIX + name
    pl = world.plugins[name]
    _teardown_module(modulename)
    if hasattr(pl, 'die'):
        try:
            pl.die(irc=irc)
        except Exception:  # A buggy die() must not abort the rehash.
            log.exception('Error in die() of plugin %r, skipping...', name)
    del world.plugins[name]
    # _load_plugin() uses import_module, which returns the cached module unless we
    # drop it here -- so this delete is what makes a subsequent load pick up edits.
    for n in (name, modulename):
        sys.modules.pop(n, None)
    gc.collect()
    return True

def load_plugin(name: str, irc=None):
    """Imports a plugin, registers it, and runs its main()."""
    world.plugins[name] = pl = utils._load_plugin(name)
    if hasattr(pl, 'main'):
        log.debug('Calling main() function of plugin %r', pl)
        pl.main(irc=irc)
    return pl

def reload_plugin(name: str, irc=None):
    """Reloads a plugin's CODE in place without tearing down what it owns. Unlike a
    full unload, this does NOT call die() -- so any service bot, relay client or other
    live connection the plugin manages stays connected across the reload. The module
    body is re-executed (picking up code edits); module-level register_service() calls
    reuse the existing live bot, and main(irc=...) lets reload-aware plugins re-sync
    against the running networks."""
    modulename = utils.PLUGIN_PREFIX + name
    module = sys.modules.get(modulename)
    _teardown_module(modulename)
    if module is None:
        # Not imported yet (newly added to the config) -- load it fresh.
        world.plugins[name] = pl = utils._load_plugin(name)
    else:
        importlib.reload(module)
        world.plugins[name] = pl = module
    if hasattr(pl, 'main'):
        log.debug('Calling main() of plugin %r (reload).', name)
        pl.main(irc=irc)
    return pl

def reload_coremod(name: str, irc=None):
    """Reloads a coremod in place with importlib.reload so that modules which import
    it keep their references working (unlike plugins, which are fully reimported)."""
    modulename = 'netlink.coremods.' + name
    module = sys.modules[modulename]
    _teardown_module(modulename)
    importlib.reload(module)
    if hasattr(module, 'main'):
        module.main(irc=irc)
    return module

def _reload_plugins(new_plugins, errors) -> None:
    """Reconciles loaded plugins against the config's plugin list. Plugins dropped from
    the config are fully unloaded (die() runs, their service bots quit -- correct, they
    should leave). Plugins still configured are reloaded IN PLACE without disconnecting
    anything they own; newly added ones are loaded fresh. Network sockets and existing
    service clients are never dropped."""
    # Fully unload (die + quit services) only the plugins removed from the config.
    for name in list(world.plugins):
        if name not in new_plugins:
            log.info('rehash: unloading plugin %r (removed from config).', name)
            try:
                unload_plugin(name)
            except Exception as e:
                log.exception('rehash: failed to unload plugin %r', name)
                errors.append('plugin %s (unload): %s: %s' % (name, type(e).__name__, e))

    # Signal reload-aware plugins (relay, automode, ...) by handing main() a live
    # network; they iterate the rest themselves and re-sync without respawning.
    reload_irc = next((i for i in world.networkobjects.values() if i.connected.is_set()), None)

    utils._reset_module_dirs()
    # Reload still-configured plugins in place; load brand-new ones.
    for name in new_plugins:
        try:
            log.info('rehash: reloading plugin %r.', name)
            reload_plugin(name, irc=reload_irc)
        except Exception as e:
            log.exception('rehash: failed to reload plugin %r', name)
            errors.append('plugin %s: %s: %s' % (name, type(e).__name__, e))

def _reload_coremods(errors) -> None:
    """Reloads every loaded coremod in place (except the stateful ones in
    UNRELOADABLE_COREMODS) so coremod code edits go live on rehash too."""
    # Snapshot the module list first -- a reload can import others mid-iteration.
    coremods = sorted({m.split('.')[2] for m in list(sys.modules)
                       if m.startswith('netlink.coremods.') and m.count('.') == 2})
    for name in coremods:
        if name in UNRELOADABLE_COREMODS:
            continue
        log.debug('rehash: reloading coremod %r.', name)
        try:
            reload_coremod(name)
        except Exception as e:
            log.exception('rehash: failed to reload coremod %r', name)
            errors.append('coremod %s: %s: %s' % (name, type(e).__name__, e))

def rehash() -> list:
    """Rehashes the NetLink daemon in place: reloads the config, all configured
    plugins and coremods, and (dis)connects added/removed networks -- WITHOUT
    dropping links that are still in the config. Returns a list of error strings
    (empty when everything reloaded cleanly)."""
    log.info('Reloading NetLink configuration...')
    errors: list = []
    fname = conf.fname
    new_conf = conf.load_conf(fname, errors_fatal=False, logger=log)
    conf.conf = new_conf

    # Reset any file logger options.
    _stop_file_loggers()
    files = new_conf['logging'].get('files')
    if files:
        for filename, config in files.items():
            _make_file_logger(filename, config.get('loglevel'))

    log.debug('rehash: updating console log level')
    world.console_handler.setLevel(_get_console_log_level())
    login._make_cryptcontext()  # refresh password hashing settings

    # Reload plugin + coremod code and apply plugin-list changes. These only touch
    # the command/hook registries and sys.modules, never the network connections.
    _reload_plugins(list(new_conf.get('plugins') or []), errors)
    _reload_coremods(errors)

    for network, ircobj in world.networkobjects.copy().items():
        # Server was removed from the config file, disconnect them.
        log.debug('rehash: checking if %r is still in new conf.', network)
        if ircobj.has_cap('virtual-server') or hasattr(ircobj, 'virtual_parent'):
            log.debug('rehash: not removing network %r since it is a virtual server.', network)
            continue

        if network not in new_conf['servers']:
            log.debug('rehash: removing connection to %r (removed from config).', network)
            remove_network(ircobj)
        else:
            # XXX: we should really just add abstraction to Irc to update config settings...
            ircobj.serverdata = new_conf['servers'][network]

            ircobj.autoconnect_active_multiplier = 1

            # Clear the IRC object's channel loggers and replace them with
            # new ones by re-running log_setup().
            while ircobj.loghandlers:
                log.removeHandler(ircobj.loghandlers.pop())

            ircobj.log_setup()

    utils._reset_module_dirs()

    for network, sdata in new_conf['servers'].items():
        # Connect any new networks or disconnected networks if they aren't already.
        if network not in world.networkobjects:
            try:
                proto = utils._get_protocol_module(sdata['protocol'])

                # API note: 2.0.x style of starting network connections
                world.networkobjects[network] = newirc = proto.Class(network)
                newirc.connect()
            except:
                log.exception('Failed to initialize network %r, skipping it...', network)

    log.info('Finished reloading NetLink configuration.')
    return errors

if os.name == 'posix':
    # Only register SIGHUP/SIGUSR1 on *nix.
    def _sighup_handler(signo, _stack_frame):
        """Handles SIGHUP/SIGUSR1 by rehashing the NetLink daemon."""
        log.info("Signal %s received, reloading config." % signo)
        rehash()

    signal.signal(signal.SIGHUP, _sighup_handler)
    signal.signal(signal.SIGUSR1, _sighup_handler)
