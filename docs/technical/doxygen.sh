#!/bin/bash
# Runs Doxygen on NetLink.

# Note: to change the outpuit path, doxygen.conf also has to be updated too!
OUTDIR="../../../netlink.github.io"

if [ ! -d "$OUTDIR" ]; then
	echo "Git clone https://github.com/NetLink/netlink.github.io to $OUTDIR and then rerun this script."
	exit 1
fi

CURDIR="$(pwd)"
doxygen doxygen.conf
cp -R html/* "$OUTDIR"
rm -r "html/"
