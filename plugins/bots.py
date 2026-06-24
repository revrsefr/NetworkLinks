"""
bots.py: Spawn virtual users/bots on a NetLink server and make them interact
with things.
"""

from __future__ import annotations
from netlink import utils
from netlink.coremods import permissions


@utils.add_cmd
def spawnclient(irc, source: str, args: list):
    """<nick> <ident> <host>

    Spawns the specified client on the NetLink server.
    Note: this doesn't check the validity of any fields you give it!"""

    if not irc.has_cap('can-spawn-clients'):
        irc.error("This network does not support client spawning.")
        return

    permissions.check_permissions(irc, source, ['bots.spawnclient'])
    try:
        nick, ident, host = args[:3]
    except ValueError:
        irc.error("Not enough arguments. Needs 3: nick, user, host.")
        return
    irc.spawn_client(nick, ident, host, manipulatable=True)
    irc.reply("Done.")

@utils.add_cmd
def quit(irc, source: str, args: list):
    """<target> [<reason>]

    Quits the NetLink client with nick <target>, if one exists."""
    permissions.check_permissions(irc, source, ['bots.quit'])

    try:
        nick = args[0]
    except IndexError:
        irc.error("Not enough arguments. Needs 1-2: nick, reason (optional).")
        return

    u = irc.nick_to_uid(nick, filterfunc=irc.is_internal_client)
    if u is None:
        irc.error("Unknown user %r" % nick)
        return

    if irc.pseudoclient.uid == u:
        irc.error("Cannot quit the main NetLink client!")
        return

    quitmsg = ' '.join(args[1:]) or 'Client Quit'

    if not irc.is_manipulatable_client(u):
        irc.error("Cannot force quit a protected NetLink services client.")
        return

    irc.quit(u, quitmsg)
    irc.reply("Done.")
    irc.call_hooks([u, 'NETLINK_BOTSPLUGIN_QUIT', {'text': quitmsg, 'parse_as': 'QUIT'}])

def joinclient(irc, source: str, args: list):
    """[<target>] <channel1>[,<channel2>,<channel3>,...] [<key1>[,<key2>,...]]

    Joins <target>, the nick of a NetLink client, to a comma-separated list of channels.
    If <target> is not given, it defaults to the main NetLink client.

    For the channel arguments, prefixes can also be specified to join the given client with
    (e.g. @#channel will join the client with op, while ~@#channel will join it with +qo.

    An optional comma-separated list of channel keys can be given as the final argument,
    aligned with the channel list, to join key-protected (+k) channels (Clientbot only).
    """
    permissions.check_permissions(irc, source, ['bots.join', 'bots.joinclient'])

    keys_arg = ''
    try:
        # Check if the first argument is an existing NetLink client. If it is not,
        # then assume that the first argument was actually the channels being joined.
        u = irc.nick_to_uid(args[0], filterfunc=irc.is_internal_client)

        if u is None:  # First argument isn't one of our clients
            raise IndexError

        clist = args[1]
        if len(args) > 2:
            keys_arg = args[2]
    except IndexError:  # No valid nick was given; shift arguments one to the left.
        u = irc.pseudoclient.uid
        try:
            clist = args[0]
        except IndexError:
            irc.error("Not enough arguments. Needs 1-3: nick (optional), comma separated list of "
                      "channels, comma separated list of keys (optional).")
            return
        if len(args) > 1:
            keys_arg = args[1]

    clist = clist.split(',')
    if not clist:
        irc.error("No valid channels given.")
        return
    keys = keys_arg.split(',') if keys_arg else []

    if not (irc.is_manipulatable_client(u) or irc.get_service_bot(u)):
        irc.error("Cannot force join a protected NetLink services client.")
        return

    prefix_to_mode = {v: k for k, v in irc.prefixmodes.items()}
    for idx, channel in enumerate(clist):
        real_channel = channel.lstrip(''.join(prefix_to_mode))
        # XXX we need a better way to do this, but only the other option I can think of is regex...
        prefixes = channel[:len(channel)-len(real_channel)]
        joinmodes = ''.join(prefix_to_mode[prefix] for prefix in prefixes)
        key = keys[idx] if idx < len(keys) and keys[idx] else None

        if not irc.is_channel(real_channel):
            irc.error("Invalid channel name %r." % real_channel)
            return

        # join() doesn't support prefixes.
        if prefixes:
            irc.sjoin(irc.sid, real_channel, [(joinmodes, u)])
        else:
            irc.join(u, real_channel, key=key)

        try:
            modes = irc.channels[real_channel].modes
        except KeyError:
            modes = []

        # Signal the join to other plugins
        irc.call_hooks([u, 'NETLINK_BOTSPLUGIN_JOIN', {'channel': real_channel, 'users': [u],
                                                     'modes': modes, 'parse_as': 'JOIN'}])
    irc.reply("Done.")
utils.add_cmd(joinclient, name='join')

@utils.add_cmd
def nick(irc, source: str, args: list):
    """[<target>] <newnick>

    Changes the nick of <target>, a NetLink client, to <newnick>. If <target> is not given, it defaults to the main NetLink client."""

    permissions.check_permissions(irc, source, ['bots.nick'])

    try:
        nick = args[0]
        newnick = args[1]
    except IndexError:
        try:
            nick = irc.pseudoclient.nick
            newnick = args[0]
        except IndexError:
            irc.error("Not enough arguments. Needs 1-2: nick (optional), newnick.")
            return
    u = irc.nick_to_uid(nick, filterfunc=irc.is_internal_client)

    if newnick in ('0', u):  # Allow /nick 0 to work
        newnick = u

    elif not irc.is_nick(newnick):
        irc.error('Invalid nickname %r.' % newnick)
        return

    elif not (irc.is_manipulatable_client(u) or irc.get_service_bot(u)):
        irc.error("Cannot force nick changes for a protected NetLink services client.")
        return

    irc.nick(u, newnick)
    irc.reply("Done.")
    # Signal the nick change to other plugins
    irc.call_hooks([u, 'NETLINK_BOTSPLUGIN_NICK', {'newnick': newnick, 'oldnick': nick, 'parse_as': 'NICK'}])

@utils.add_cmd
def part(irc, source: str, args: list):
    """[<target>] <channel1>,[<channel2>],... [<reason>]

    Parts <target>, the nick of a NetLink client, from a comma-separated list of channels. If <target> is not given, it defaults to the main NetLink client."""
    permissions.check_permissions(irc, source, ['bots.part'])

    try:
        nick = args[0]
        clist = args[1]
        # For the part message, join all remaining arguments into one text string
        reason = ' '.join(args[2:])

        # First, check if the first argument is an existing NetLink client. If it is not,
        # then assume that the first argument was actually the channels being parted.
        u = irc.nick_to_uid(nick, filterfunc=irc.is_internal_client)
        if u is None:  # First argument isn't one of our clients
            raise IndexError

    except IndexError:  # No nick was given; shift arguments one to the left.
        u = irc.pseudoclient.uid

        try:
            clist = args[0]
        except IndexError:
            irc.error("Not enough arguments. Needs 1-2: nick (optional), comma separated list of channels.")
            return
        reason = ' '.join(args[1:])

    clist = clist.split(',')
    if not clist:
        irc.error("No valid channels given.")
        return

    if not (irc.is_manipulatable_client(u) or irc.get_service_bot(u)):
        irc.error("Cannot force part a protected NetLink services client.")
        return

    for channel in clist:
        if not irc.is_channel(channel):
            irc.error("Invalid channel name %r." % channel)
            return
        irc.part(u, channel, reason)

    irc.reply("Done.")
    irc.call_hooks([u, 'NETLINK_BOTSPLUGIN_PART', {'channels': clist, 'text': reason, 'parse_as': 'PART'}])

def msg(irc, source: str, args: list):
    """[<source>] <target> <text>

    Sends message <text> from <source>, where <source> is the nick of a NetLink client. If <source> is not given, it defaults to the main NetLink client."""
    permissions.check_permissions(irc, source, ['bots.msg'])

    # Because we want the source nick to be optional, this argument parsing gets a bit tricky.
    try:
        msgsource = args[0]
        target = args[1]
        text = ' '.join(args[2:])

        # First, check if the first argument is an existing NetLink client. If it is not,
        # then assume that the first argument was actually the message TARGET.
        sourceuid = irc.nick_to_uid(msgsource, filterfunc=irc.is_internal_client)

        if sourceuid is None or not text:  # First argument isn't one of our clients
            raise IndexError

    except IndexError:
        try:
            sourceuid = irc.pseudoclient.uid
            target = args[0]
            text = ' '.join(args[1:])
        except IndexError:
            irc.error('Not enough arguments. Needs 2-3: source nick (optional), target, text.')
            return

    if not text:
        irc.error('No text given.')
        return

    try:
        int_u = int(target)
    except:
        int_u = None

    if int_u and int_u in irc.users:
        real_target = int_u  # Some protocols use numeric UIDs
    elif target in irc.users:
        real_target = target
    elif not irc.is_channel(target):
        # Convert nick of the message target to a UID, if the target isn't a channel or UID
        potential_targets = irc.nick_to_uid(target, multi=True)
        if not potential_targets:  # Unknown target user, if target isn't a valid channel name
            irc.error('Unknown user %r.' % target)
            return
        elif len(potential_targets) > 1:
            irc.error('Multiple users with the nick %r found: please select the right UID: %s' % (target, str(potential_targets)))
            return
        else:
            real_target = potential_targets[0]
    else:
        real_target = target

    irc.message(sourceuid, real_target, text)
    irc.reply("Done.")
    irc.call_hooks([sourceuid, 'NETLINK_BOTSPLUGIN_MSG', {'target': real_target, 'text': text, 'parse_as': 'PRIVMSG'}])
utils.add_cmd(msg, aliases=('say',))
