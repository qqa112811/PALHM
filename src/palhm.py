#!/usr/bin/env python3
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
import importlib
import logging
import os
import sys
from abc import ABC, abstractmethod
from getopt import getopt

import palhm
from palhm.exceptions import InvalidConfigError


class ProgConf:
	conf = "/etc/palhm/palhm.jsonc"
	cmd = None
	override_vl = None
	ctx = None

	def alloc_ctx ():
		ProgConf.ctx = palhm.setup_conf(palhm.load_conf(ProgConf.conf))
		if not ProgConf.override_vl is None:
			ProgConf.ctx.l.setLevel(ProgConf.override_vl)

def err_unknown_cmd ():
	sys.stderr.write("Unknown command. Run '" + sys.argv[0] + " help' for usage.\n")
	exit(2)

class Cmd (ABC):
	@abstractmethod
	def do_cmd (self):
		...

class ConfigCmd (Cmd):
	def __init__ (self, *args, **kwargs):
		pass

	def do_cmd (self):
		ProgConf.alloc_ctx()
		print(ProgConf.ctx)
		return 0

	def print_help ():
		print(
"Usage: " + sys.argv[0] + " config" + '''
Load and parse config. Print the structure to stdout.''')

class RunCmd (Cmd):
	def __init__ (self, optlist, args):
		self.optlist = optlist
		self.args = args

	def do_cmd (self):
		ProgConf.alloc_ctx()

		if self.args and self.args[0]: # empty string as "default"
			task = self.args[0]
		else:
			task = palhm.DEFAULT.RUN_TASK.value

		ProgConf.ctx.task_map[task].run(ProgConf.ctx)

		return 0

	def print_help ():
		print(
"Usage: " + sys.argv[0] + " run [TASK]" + '''
Run a task in config. Run the "''' + palhm.DEFAULT.RUN_TASK.value +
'''" task if [TASK] is not specified.''')

class ModsCmd (Cmd):
	def __init__ (self, *args, **kwargs):
		pass

	def _walk_mods (self, path: str):
		def is_mod_dir (path: str) -> bool:
			try:
				for i in os.scandir(path):
					if i.name.startswith("__init__.py"):
						return True
			except NotADirectoryError:
				pass
			return False

		def is_mod_file (path: str) -> str:
			if not os.path.isfile(path):
				return None

			try:
				pos = path.rindex(".")
				if path[pos + 1:].startswith("py"):
					return os.path.basename(path[:pos])
			except ValueError:
				pass

		for i in os.scandir(path):
			if i.name.startswith("_"):
				continue
			elif is_mod_dir(i.path):
				print(i.name)
				self._walk_mods(i.path)
			else:
				name = is_mod_file(i.path)
				if name:
					print(name)

	def do_cmd (self):
		for i in importlib.util.find_spec("palhm.mod").submodule_search_locations:
			self._walk_mods(i)

		return 0

	def print_help ():
		print(
"Usage: " + sys.argv[0] + " mods" + '''
Prints the available modules to stdout.''')

class BootReportCmd (Cmd):
	def __init__ (self, *args, **kwargs):
		pass

	def do_cmd (self):
		ProgConf.alloc_ctx()

		if ProgConf.ctx.boot_report is None:
			raise InvalidConfigError("'boot-report' not configured")

		return ProgConf.ctx.boot_report.do_send(ProgConf.ctx)

	def print_help ():
		print(
"Usage: " + sys.argv[0] + " boot-report" + '''
Send mail of boot report to recipients configured.''')

class HelpCmd (Cmd):
	def __init__ (self, optlist, args):
		self.optlist = optlist
		self.args = args

	def do_cmd (self):
		if len(self.args) >= 2:
			if not args[0] in CmdMap:
				err_unknown_cmd()
			else:
				CmdMap[self.args[0]].print_help()
		else:
			HelpCmd.print_help()

		return 0

	def print_help ():
		print(
"Usage: " + sys.argv[0] + " [options] CMD [command options ...]" + '''
Options:
  -q       Set the verbosity level to 0(CRITIAL). Overrides config
  -v       Increase the verbosity level by 1. Overrides config
  -f FILE  Load config from FILE instead of the hard-coded default
Config: ''' + ProgConf.conf + '''
Commands:
  run          run a task
  config       load config and print the contents
  help [CMD]   print this message and exit normally if [CMD] is not specified.
               Print usage of [CMD] otherwise
  mods         list available modules
  boot-report  mail boot report''')

		return 0

CmdMap = {
	"config": ConfigCmd,
	"run": RunCmd,
	"help": HelpCmd,
	"mods": ModsCmd,
	"boot-report": BootReportCmd
}

optlist, args = getopt(sys.argv[1:], "qvf:")
optkset = set()
for p in optlist:
	optkset.add(p[0])

if "-v" in optkset and "-q" in optkset:
	sys.stderr.write("Options -v and -q cannot not used together.\n")
	exit(2)

if not args or not args[0] in CmdMap:
	err_unknown_cmd()

for p in optlist:
	if p[0] == "-q": ProgConf.override_vl = logging.ERROR
	elif p[0] == "-v":
		if ProgConf.override_vl is None:
			ProgConf.override_vl = palhm.DEFAULT.VL.value - 10
		else:
			ProgConf.override_vl -= 10
	elif p[0] == "-f": ProgConf.conf = p[1]

logging.basicConfig(format = "%(name)s %(message)s")

ProgConf.cmd = CmdMap[args[0]](optlist, args)
del args[0]
exit(ProgConf.cmd.do_cmd())
