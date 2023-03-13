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
from concurrent.futures import ThreadPoolExecutor, Future
from decimal import Decimal
from enum import Enum
from time import sleep
from typing import Callable, Iterable

import boto3
import botocore
from palhm import MUA, BackupBackend, BackupObject, Exec, GlobalContext
from palhm.exceptions import APIFailError


class CONST (Enum):
	AWSCLI = "/bin/aws"

def mks3objkey (keys: Iterable[str]) -> str:
	ret = "/".join(keys)
	return ret.strip("/")

def mks3uri (bucket: str, keys: Iterable[str]) -> str:
	return "s3://" + bucket + "/" + "/".join(keys)

class S3BackupBackend (BackupBackend):
	def __init__ (self, param: dict):
		self.profile = param.get("profile", "default")
		self.bucket = param["bucket"]
		self.root_key = mks3objkey([param["root"]])
		self.mkprefix = BackupBackend.mkprefix_iso8601
		self.nb_copy_limit = Decimal(param.get("nb-copy-limit", "Infinity"))
		self.root_size_limit = Decimal(param.get("root-size-limit", "Infinity"))
		self.cur_backup_uri = None
		self.cur_backup_key = None
		self.sc_sink = param.get("sink-storage-class")
		self.sc_rot = param.get("rot-storage-class")
		self.client = None
		self.sink_list = list[str]()

	def _setup_cur_backup (self, ctx: GlobalContext):
		self.cur_backup_key = mks3objkey([self.root_key, self.mkprefix()])
		self.cur_backup_uri = mks3uri(self.bucket, [self.cur_backup_key])

	def open (self, ctx: GlobalContext):
		self.client = boto3.Session(profile_name = self.profile).client("s3")

		try:
			for i in range(0, 2):
				self._setup_cur_backup(ctx)
				# This should raise
				self.client.head_object(
					Bucket = self.bucket,
					Key = self.cur_backup_key)
				sleep(1)
			# Make sure we don't proceed
			raise FileExistsError(
				"Failed to set up a backup dir. Check the prefix function",
				self.cur_backup_uri)
		except botocore.exceptions.ClientError as e:
			c = e.response["Error"]["Code"]
			if c != "404": # expected status code
				raise APIFailError("Unexpected status code", c)

		return super().open(ctx)

	def _cleanup_multiparts (self, ctx: GlobalContext) -> bool:
		def do_abort (e):
			try:
				self.client.abort_multipart_upload(
					Bucket = self.bucket,
					Key = e["Key"],
					UploadId = e["UploadId"])
			except: pass

		cont = None
		fl = list[Future]()

		with ThreadPoolExecutor(max_workers = ctx.nb_workers) as th_pool:
			while True:
				if cont:
					r = self.client.list_multipart_uploads(
						Bucket = self.bucket,
						Prefix = self.cur_backup_key,
						KeyMarker = cont[0],
						UploadIdMarker = cont[1])
				else:
					r = self.client.list_multipart_uploads(
						Bucket = self.bucket,
						Prefix = self.cur_backup_key)

				for i in r.get("Uploads", iter(())):
					fl.append(th_pool.submit(do_abort, i))
				for i in fl:
					i.result()
				fl.clear()

				if r["IsTruncated"]:
					cont = (r["NextKeyMarker"], r["UploadIdMarker"])
				else:
					break

	def _foreach_objs (self, ctx: GlobalContext, prefix: str, cb: Callable):
		cont_token = None

		if not prefix.endswith("/"): prefix += "/"

		while True:
			if cont_token:
				r = self.client.list_objects_v2(
					Bucket = self.bucket,
					Prefix = prefix,
					ContinuationToken = cont_token)
			else:
				r = self.client.list_objects_v2(
					Bucket = self.bucket,
					Prefix = prefix)

			for i in r["Contents"]:
				cb(i)

			if r["IsTruncated"]:
				cont_token = r["NextContinuationToken"]
			else:
				break

	def _fs_usage_info (self, ctx: GlobalContext) -> Iterable[tuple[str, int]]:
		du_map = dict[str, int]()
		ret = list[tuple[str, int]]()
		prefix = self.root_key + "/"
		def cb (i):
			o_key = i["Key"]
			o_size = i.get("Size", 0)
			if not o_key.startswith(self.root_key):
				raise APIFailError(
					"The endpoint returned an object irrelevant to the request",
					o_key)

			l = o_key.find("/", len(prefix))
			if l >= 0:
				o_backup = o_key[:l]
			else:
				return

			du_map[o_backup] = du_map.get(o_backup, 0) + o_size

		self._foreach_objs(ctx, prefix, cb)
		for i in sorted(du_map.keys()):
			ret.append((i, du_map[i]))

		return ret

	def _excl_fs_copies (self, ctx: GlobalContext) -> set[str]:
		ret = set[str]()
		ret.add(self.cur_backup_key)
		return ret

	def _rm_fs_recursive (self, ctx: GlobalContext, pl: Iterable[str]):
		l = self._logger(ctx)

		with ThreadPoolExecutor(max_workers = ctx.nb_workers) as th_pool:
			fl = list[Future]()

			for i in pl:
				e = Exec()
				e.argv = [
					CONST.AWSCLI.value,
					"--profile=" + self.profile,
					"s3",
					"rm",
					"--quiet",
					"--recursive",
					mks3uri(self.bucket, [i]) ]
				l.debug("run: " + str(e))
				fl.append(th_pool.submit(e.run, ctx))
			for i in fl:
				i.result()

	def _fs_quota_target (self, ctx: GlobalContext) -> tuple[Decimal, Decimal]:
		return (self.nb_copy_limit, self.root_size_limit)

	def rollback (self, ctx: GlobalContext):
		if not self.cur_backup_uri is None:
			self._rm_fs_recursive(ctx, [self.cur_backup_key])

	def close (self, ctx: GlobalContext):
		self._cleanup_multiparts(ctx)

	def sink (self, ctx: GlobalContext, bo) -> Exec:
		l = self._logger(ctx)

		e = Exec()
		e.argv = [
			CONST.AWSCLI.value,
			"--profile=" + self.profile,
			"s3",
			"cp",
			"--only-show-errors" ]
		if self.sc_sink:
			e.argv.append("--storage-class=" + self.sc_sink)
		if bo.alloc_size is not None:
			e.argv.append("--expected-size=" + str(bo.alloc_size))
		e.argv.extend(["-", "/".join([self.cur_backup_uri, bo.path])])

		l.debug("sink: " + str(e))
		self.sink_list.append(mks3objkey([self.cur_backup_key, bo.path]))

		return e

	def rotate (self, ctx: GlobalContext):
		ret = super()._do_fs_rotate(ctx)

		if self.sc_rot and self.sc_rot != self.sc_sink:
			def chsc (k):
				cp_src = {
					"Bucket": self.bucket,
					"Key": k
				}
				extra = { "StorageClass": self.sc_rot }
				self.client.copy(cp_src, self.bucket, k, extra)

			with ThreadPoolExecutor(max_workers = ctx.nb_workers) as th_pool:
				l = self._logger(ctx)
				fl = list[Future]()

				for i in self.sink_list:
					l.debug("chsc: %s %s" % (self.sc_rot, i))
					fl.append(th_pool.submit(chsc, i))
				for i in fl:
					i.result()

		return ret

	def __str__ (self):
		return '''aws-s3:
	profile: {profile}
	bucket: {bucket}
	root_key: {root_key}
	nb_copy_limit: {nb_copy_limit}
	root_size_limit: {root_size_limit}
	sc_sink: {sc_sink}
	sc_rot: {sc_rot}'''.format(
		profile = self.profile,
		bucket = self.bucket,
		root_key = self.root_key,
		nb_copy_limit = self.nb_copy_limit,
		root_size_limit = self.root_size_limit,
		sc_sink = self.sc_sink,
		sc_rot = self.sc_rot)

class AwsSnsMUA (MUA):
	def __init__ (self, jobj: dict):
		self.profile = jobj.get("profile", "default")
		self.region = jobj.get("region", None)

	def __str__ (self) -> str:
		return '''aws-sns:
	profile: {profile}
	region: {region}'''.format(
		profile = self.profile,
		region = self.region)

	def do_send(
		self,
		ctx: GlobalContext,
		recipients: Iterable[str],
		subject: str,
		composer: Iterable[str]) -> int:
		lines = list[str]()
		client = boto3.Session(
			profile_name = self.profile,
			region_name = self.region).client("sns")

		for l in composer:
			lines.append(l)

		for i in recipients:
			client.publish(
				TargetArn = i,
				Subject = subject,
				Message = "".join(lines))

		return 0

muas = {
	"aws-sns": AwsSnsMUA
}

backup_backends = {
	"aws-s3": S3BackupBackend
}
