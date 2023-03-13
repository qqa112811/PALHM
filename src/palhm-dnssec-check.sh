#!/bin/bash

# This script is a legacy. The same functionality can be implemented by setting
# up a back up task. See [conf/py-sample/sample.jsonc]

# Copyright (c) 2022 David Timber <dxdt@dev.snart.me>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

do_query () {
	# dig returns 0 upon successful reception and parse of the response message.
	# All the other exit codes other than 0 will cause the script to terminate
	# as a result of set -e. +short option makes dig return the values of RR.
	# We assume that a status code has returned when dig produces no output with
	# the option. Caution must be taken in this approach as zones with no
	# record will also return nothing with the status code zero.
	dig +short +dnssec +notcp ANY "$TARGET" > "$tmpf"
	if [ ! -s "$tmpf" ]; then
		echo "The nameserver returned no RR!
DNSSEC verification probably failed." >&2
		exit 1
	fi
}

if [ "$#" -lt 1 ]; then
	cat >&2 << EOF
The Periodic Automatic Linux Host Maintenance (PALHM) DNSSEC check
Usage: $0 <record name>

The zone must contain at least one resource record set. The nameservers
configured for the host must support DNSSEC validation.

To test your host configuration, running
  \$ $0 dnssec-failed.org
should produce error messages.
EOF
	exit 2
fi

declare TARGET="$1"
declare tmpf="$(mktemp --tmpdir "palhm-dnssec.XXXXXXXXXX")"

do_query & set +e
wait
ec="$?"
rm "$tmpf"

exit "$ec"
