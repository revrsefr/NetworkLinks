"""
world.py: Stores global variables for NetLink, including lists of active IRC objects and plugins.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Any

__all__ = [
           'daemon',
           'exttarget_handlers',
           'fallback_hostname',
           'hooks',
           'networkobjects',
           'plugins',
           'services',
           'shutting_down',
           'source',
           'start_ts',
           'started',
           'testing',
]

# This indicates whether we're running in tests mode. What it actually does
# though is control whether IRC connections should be threaded or not.
testing = False

# The console log handler, assigned by log.py at import time.
console_handler: Any = None

# Statekeeping for our hooks list, IRC objects, loaded plugins, and initialized
# service bots.
hooks: defaultdict = defaultdict(list)
networkobjects: dict = {}
plugins: dict = {}
services: dict = {}

# Registered extarget handlers. This maps exttarget names (strings) to handling functions.
exttarget_handlers: dict = {}

# Trigger to be set when all IRC objects are initially created.
started = threading.Event()

# Global daemon starting time.
start_ts = time.time()

# Trigger to set on shutdown.
shutting_down = threading.Event()

# Source address.
source = "https://github.com/revrsefr/NetworkLinks"  # CHANGE THIS IF YOU'RE FORKING!!

# Fallback hostname used in various places internally when hostname isn't configured.
fallback_hostname = 'netlink.int'

# Defines messages to be logged as soon as the log system is set up, for modules like conf that are
# initialized before log. This is processed (and then not used again) when the log module loads.
_log_queue: deque = deque()

# Determines whether we have a PID file that needs to be removed.
_should_remove_pid = False

# Determines whether we're daemonized.
daemon = False
