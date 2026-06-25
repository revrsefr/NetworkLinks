# Note: Service support has to be imported first, so that utils.add_cmd() works for corecommands,
# etc.
from . import service_support, permissions, control, handlers, corecommands, exttargets

# Imported for their registration side effects; re-exported so the package's public
# surface is explicit (and to mark the imports above as intentional, not unused).
__all__ = ['control', 'corecommands', 'exttargets', 'handlers', 'permissions', 'service_support']
