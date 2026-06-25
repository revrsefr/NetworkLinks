# NetLink

**NetLink** is an extensible IRC services framework and transparent inter-network relayer. It can:

1. act as a **server-side relay** that transparently mirrors channels between IRC networks, and
2. host **services** — a programmable services bot with a plugin API.

NetLink is a modernized, slimmed-down derivative of PyLink, focused on current IRCds with full IRCv3 message-tag support (TAGMSG, server-time, message-tags).

## Supported IRCds

| IRCd | Versions | Protocol module |
|------|----------|-----------------|
| [InspIRCd](https://www.inspircd.org/) | **4.x** | `inspircd` |
| [UnrealIRCd](https://www.unrealircd.org/) | **6.x** | `unreal` |
| Clientbot (relay leaf only) | any | `clientbot` |

NetLink targets **InspIRCd 4** and **UnrealIRCd 6** for server-to-server links. Support for older
protocols (TS6/charybdis/ratbox, P10/Nefarious/snircd, IRCd-Hybrid, ngIRCd, and pre-4 InspIRCd /
pre-6 UnrealIRCd) has been removed — those drivers are gone.

### Clientbot — relaying without a server link

For networks you can't or don't want to server-link with, **Clientbot** connects to the network as
a normal IRC bot and relays users back as virtual clients. Load the `relay_clientbot` plugin
alongside `relay`. Clientbot links can only be **relay leaves** — they cannot host channels — so you
can't build a relay entirely out of Clientbot links.

## Requirements

- Python **3.9+**
- [PyYAML](https://pypi.org/project/PyYAML/) and [cachetools](https://pypi.org/project/cachetools/)
- Optional: [passlib](https://pypi.org/project/passlib/) (>= 1.7.0) for hashed account passwords

## Installation (from source)

```sh
git clone https://github.com/revrsefr/NetworkLinks netlink && cd netlink
python3 -m venv run
run/bin/pip install -e '.[password-hashing]'
```

This installs the `netlink` launcher and the `netlink-mkpasswd` password helper into `run/bin/`.
Optional extras: `password-hashing` (passlib — hashed account passwords), `relay-unicode`
(unidecode — nicer relay nick transliteration), and `cron-support` (psutil).

## Configuration

Copy `example-conf.yml` to your own config (e.g. `netlink.yml`) and edit the `netlink:`, `login:`,
and `servers:` blocks. On the IRCd side, add a matching `<link>` block (InspIRCd) or `link {}` block
(UnrealIRCd) with the same server name and send/recv passwords. Then:

```sh
run/bin/netlink run/netlink.yml          # run in the foreground
run/bin/netlink -d run/netlink.yml       # daemonize
run/bin/netlink -s run/netlink.yml       # stop
run/bin/netlink -R run/netlink.yml       # rehash
```

A rehash reloads the configuration **and** all plugins and coremods in place, only
(dis)connecting servers that were added to or removed from the config — existing server
links are never dropped. If you run NetLink under systemd, `systemctl reload` does the same.

Hash account passwords with:

```sh
run/bin/netlink-mkpasswd
```

## Documentation

See the [`docs/`](docs/) directory for relay setup, services configuration, permissions, exttargets,
and the plugin/protocol developer reference.

## Development

There is no hosted CI; quality is enforced by a local gate. From a checkout:

```sh
make dev            # create .venv and install dev tooling + the package (editable)
make check          # ruff + mypy + pytest -- keep this green
make install-hooks  # run the gate automatically before every commit
```

Individual steps are available as `make lint`, `make test`, `make typecheck`, and
`make coverage`. The ruff and mypy configuration lives in `pyproject.toml`.

## Credits & license

NetLink is a derivative work of **[PyLink](https://github.com/jlu5/PyLink)** by James Lu and
contributors, used under the Mozilla Public License 2.0. The original copyright and contributor
credits are preserved in [`AUTHORS`](AUTHORS); NetLink itself is likewise licensed under the
[MPL-2.0](LICENSE.MPL2). Documentation is under [CC BY-SA 4.0](LICENSE.CC-BY-SA-4.0).
