# Periodic Automatic Live Host Maintenance (PALHM)
This is a script that automates periodic maintenance of a machine. PALHM covers
a routinely sequential command run as well as "hot" or "live" back up of the
running host to a backend of your choice.

PALHM addresses problems of the traditional lazy method of making a copy of the
entirety of drives.

* Use of high-level data dump tools like mysqldump and slapcat
* Not including data obtainable from the modern package manager such as the
  contents of /usr to reduce cost
* Dump of metadata crucial when restoring from backup via use of tools like
  lsblk

The safest way to back up has always been by getting the system offline and
tar'ing the file system or making an image of the storage device. This may not
be practical in set ups where downtime is unacceptable or allocating more
resources for a backup task is not cost-efficient. This is where this script
comes in to play.

## TL;DR
Goto [#Getting Started](#getting-started).

## Routine Task
The Routine Task is a set of routines that are executed sequentially. It can
consist of commands(Execs) and other previously defined tasks. Routine Tasks are
absolute basic - you may incorporate custom shell scripts or other executables
to do complex routines.

## Backup Task
PALHM supports backup on different storage backends. It also automates rotation
of backup copies on the supported storage backends. **aws-s3** and **localfs**
are currently implemented. You may incorporate localfs to store backups on NFS
or Samba mount points. The special **null** backend is for testing purposes.

The files produced as end product of backup are called "Backup Objects". The
Backup Objects have two essential attributes.

* **pipeline**: commands used to generate the backup output file
* **path**: path to the output file on the backend
* **alloc-size**: expected size of the object. Recommended for some backends
  like AWS in order to determine the transfer block size

For example, this object definition is for a mysql data dump compressed in zstd
and encrypted using a public key id "backup-pub-key" named as
"all-db.sql.zstd.pgp".

```jsonc
{
  "path": "all-db.sql.zstd.pgp",
  "alloc-size": 268435456, // 256MiB
  "pipeline": [
    { "type": "exec-inline", "argv": [ "/bin/mysqldump", "-uroot", "--all-databases" ] },
    { "type": "exec-inline", "argv": [ "/bin/zstd" ] },
    { "type": "exec-inline", "argv": [ "/bin/gpg", "-e", "-r", "backup-pub-key", "--compress-algo", "none" ] }
  ]
}
```

This is equivalent of doing this from the shell

```sh
mysqldump -uroot --all-databases | zstd | gpg -e -r backup-pub-key --compress-algo none > all-db.sql.zstd.pgp
```

except that the output file can be placed on the cloud service depending on the
backend used. The frequently used commands like "compression filters" are
defined in the core
config([conf.d/core.json](src/conf/py-sample/conf.d/core.json)) as Exec
definitions.

### Backup Object Path
The final path for a Backup Object is formulated as follows.

```
localfs:
 /media/backup/localhost/2022-05-01T06:59:17+00:00/all-db.sql.zstd.pgp
|         ROOT          |         PREFIX          |       PATH        |

aws-s3:
 s3://your-s3-bucket/backup/your-host/2022-05-01T06:59:17+00:00/all-db.sql.zstd.pgp
     |    BUCKET    |      ROOT      |         PREFIX          |       PATH        |
```

| ATTR | DESC |
| - | - |
| ROOT | The root directory for backup |
| PREFIX | The name of the backup |
| PATH | The output path of the backup object |

The default format of PREFIX is the output of `date --utc --iso-8601=seconds`.
Backup rotation is performed using PREFIX. The PREFIX must be based on values
that, when sorted in ascending order, the oldest backup should appear first.

PATH may contain the directory separator("/" or "\\"). The backend may or may
not support this. The localfs backend handles this by doing `mkdir -p` on path
before creating a "sink" for output files. Using "/" for PATH on Windows will
fail as per NTFS limitation. The aws-s3 backend will pass the directory
separator "/" through to Boto3 API and sub directory objects will be created
implicitly.

### Backend-param
The parameters specific to backup backends can be set using backend-param. Here
are parameters commonly appear across backends.

* root: (string) the path to the backup root
* nb-copy-limit: (decimal) the number of most recent backups to keep
* root-size-limit: (decimal) the total size of the backup root in bytes
* prefix: (TODO) reserved for future

The value of the decimal type is either a JSON number or a string that
represents a decimal number. The IEEE754 infinity representation("inf",
"Infinity", "-inf" or "-Infinity") can be used for *nb-copy-limit* and
*root-size-limit* to disable both or either of the attributes. The decimal type
is not affected by the limit of IEEE754 type(the 2^53 integer part). The
fractional part of the numbers are ignored as they are compared against the
integers.

#### Localfs
```jsonc
{
  "tasks": [
    {
      "id": "backup",
      "type": "backup",
      "backend": "localfs",
      "backend-param": {
        "root": "/media/backup/localhost", // (REQUIRED)
        "dmode": "755", // (optional) mode for new directories
        "fmode": "644", // (optional) mode for new files
        "nb-copy-limit": "Infinity", // (optional)
        "root-size-limit": "Infinity", // (optional)
        "block-size": 8388608 // 16MiB: (optional)block size for underlying dd command
      },
      "object-groups": [ /* ... */ ],
      "objects": [ /* ... */ ]
    }
  ]
}
```

#### aws-s3
```jsonc
{
  "tasks": [
    {
      "id": "backup",
      "type": "backup",
      "backend": "aws-s3",
      "backend-param": {
        "profile": "default", // (optional) AWS client profile. Defaults to "default"
        "bucket": "palhm.test", // (REQUIRED) S3 bucket name
        "root": "/palhm/backup", // (REQUIRED)
        "sink-storage-class": "STANDARD", // (optional) storage class for new uploads
        "rot-storage-class": "STANDARD", // (optional) storage class for final uploads
        "nb-copy-limit": "Infinity", // (optional)
        "root-size-limit": "Infinity" // (optional)
      },
      "object-groups": [ /* ... */ ],
      "objects": [ /* ... */ ]
    }
  ]
}
```

For profiles configured for root, see `~/.aws/config`. Run `aws configure help`
for more info.

For possible values for storage class, run `aws s3 cp help`.

If you wish to keep backup copies in Glacier, you may want to upload backup
objects as STANDARD first and change the storage class to GLACIER on the rotate
stage because in the event of failure, PALHM rolls back the process by deleting
objects already uploaded to the bucket. You may be charged for the objects
stored in Glacier as the minimum storage duration is 90 days(as of 2022). The
**rot-storage-class** attribute serves this very purpose. More info on [the
pricing page](https://aws.amazon.com/s3/pricing/).

### Backup Object Dependency Tree
Backup objects can be configured to form a dependency tree like Makefile
objects. By default, PALHM builds backup files simultaneously(*nb-workers*). On
some environments, this may not be desirable, especially on system with
HDDs[^1]. You can tune this behaviour by either ...

* Setting *nb-workers* to 1
* Grouping the backup objects so that the objects from one storage device are
  built sequentially

Say the system has one storage device that holds all data necessary for service
and another one on which OS is installed. The system services static HTTP, MySQL
and OpenLDAP. All the backup tasks need to be grouped separately in order to
reduce IO seek time.

```jsonc
{
  "object-groups": [
    { "id": "root" },
    { "id": "http" },
    { "id": "sql", "depends": [ "http" ] },
    { "id": "ldap", "depends": [ "sql" ] },
  ]
}
```

On start, the objects in "root" and "http" groups will be built simultaneously.
On completion of all the objects in "http", the objects in the group "sql" and
"ldap" will be built in order.

## Boot Report Mail
PALHM supports sending the "Boot Report Mail", which contains information about
the current boot. The mail is meant to be sent on boot up for system admins to
ensure no unexpected reboot event will go uninvestigated. This feature is used
in conjunction with [the systemd service](src/conf/palhm-boot-report.service)
or a rc.d script on SysVinit based systems.

```jsonc
{
  "boot-report": {
   // (REQUIRED) MUA for sending mail
   /* stdout MUA
    * For testing. Print contents to stdout. Doesn't actually send mail
    */
    // "mua": "stdout",
    "mua": "mailx", // mailx command MUA
   // (REQUIRED) List of recipients
    "mail-to": [ "root" ],
   // The mail subject (optional)
    "subject": "Custom Boot Report Subject from {hostname}",
   /*
    * The mail body header(leading yaml comments). Use line break(\n) for
    * multi-line header (optional)
    */
    "header": "Custom header content with {hostname} substitution.",
    "uptime-since": true, // Include output of `uptime --since` (optional)
    "uptime": true, // Include output of `uptime -p` (optional)
    "bootid": true, // Include kernel boot_id (optional)
    // Wait for systemd to finish boot up process (optional)
    "boot-wait": "systemd",
    // Wait 5 seconds before sending mail
    "delay": 5
  }
}
```

### AWS SNS MUA
The boot report can be sent to a AWS SNS topic. The `aws-sns` MUA comes with
the `aws` module.

```jsonc
{
  "modules": [ "aws" ],
  "boot-report": {
    "mua": "aws-sns",
    "mua-param": {
      // "profile": "default",
      // If the profile does not have the default region.
      "region": "us-east-1"
    },
    // Target ARNs. Any ARN recognised by the SNS can be used.
    "mail-to": [ "arn:aws:sns:us-east-1:NNNNNNNNNNNN:topic-test" ]
  }
}
```

## DNSSEC Check
If your domain is configured with DNSSEC, PALHM can be used to check the
reachability of your RRs. Your domain will become unavailable when the keys are
misconfigured or you have missed the mandatory key rollover event.

The DNSSEC Check task can be fabricated as backup tasks. This replaces the
original [palhm-dnssec-check.sh](src/palhm-dnssec-check.sh) script. The upstream
name servers must support DNSSEC. The task can be run from crontab. PALHM will
produce stderr output and return non-zero exit code, causing crond to send mail.

```jsonc
{
  "tasks": [
    {
      "id": "check-dnssec",
      "type": "backup",
      "backend": "null",
      "objects": [
        {
          "path": "example.com", // Placeholder
          "pipeline": [
            /*
            * Check if dig can query the record with the DNSSEC
            * validation flag. Empty stdout with zero return code
            * means SERVFAIL.
            */
            {
              "type": "exec-append",
              "exec-id": "dig-dnssec",
              "argv": [ "ANY", "example.com" ]
            },
            /*
             * Trap for empty dig output grep will return non-zero if
             * dig have not produced any output
             */
            { "type": "exec", "exec-id": "grep-any" }
          ]
        }
      ]
    }
  ]
}
```

Here's the example crontab.

```crontab
0  *  *  *  *   root systemd-run -qP -p User=palhm -p Nice=15 -p ProtectSystem=strict -p ReadOnlyPaths=/ -p PrivateDevices=true --wait /var/lib/PALHM/src/palhm.py -q run check-dnssec
```

## Config JSON Format
See [doc/config-fmt.md](doc/config-fmt.md).

## Getting Started
The tasks can be run with the "run" subcommand. Run
'[src/palhm.py](src/palhm.py)' help for more.

```sh
palhm.py run
# For crontab job
palhm.py -q run
palhm.py -q run check-dnssec
```

### Prerequisites
* Python 3.9 or higher
* `json_reformat` command provided by **yajl** for jsonc support (optional)
* **awscli** and **boto3** for aws-s3 backup backend (optional)

### Examples
* [sample.jsonc](src/conf/py-sample/sample.jsonc)
* [crontab](src/conf/crontab)
* [systemd service](src/conf/palhm-boot-report.service) for Boot Report

## Files
| Path | Desc |
| - | - |
| /etc/palhm/palhm.conf | The default config path |
| /etc/palhm/conf.d/core.json | Commonly used Exec and Prefix definitions |

## Troubleshoot
### Large Files on AWS S3
To fit awscli into the pipelining design, the sink data is fed via stdin of
awscli. As a result, uploading files larger than 80GiB will fail without
following measures.

- Specifying `alloc-size` for large backup objects so that awscli can determine
  the optimal multipart size
- Increasing the default multipart size in config
  - E.g. `aws configure set default.s3.multipart_chunksize 32MiB` will increase
    the max to 320GiB (32MiB * 10000)

## Advanced
### Testing Config
When writing backup task, if you're worried about data loss caused by
misconfiguration or vulnerabilities, you can use [systemd's
sandboxing](https://www.freedesktop.org/software/systemd/man/systemd.exec.html#Sandboxing)
to test out your config. The distro must be running Systemd in order for this to
work.

```sh
systemd-run -qP -p Nice=15 -p ProtectSystem=strict -p ReadOnlyPaths=/ -p PrivateDevices=true --wait /usr/local/bin/palhm.py run backup
```

If your config runs on a read-only file system, it's safe to assume that the
config does not require a read-write file system in order to run. This means
your config does not modify the file system.

Also, you can always do a dry run of your backup task by setting the backend to
"**null**".

## TODO
* JSON schema validation

### AWS S3 Replication Daemon
To prepare for very unlikely events of
[disasters](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
affecting an entire AWS region, you may wish to implement cross-region
replication of S3 objects. Contrary to the document's recommendation, the
replication the S3 provides does not work on very large objects. So replication
of large objects across AWS regions has to be done manually by a client -
another implementation is required.

Cross-region data transfer is costly, so this idea came to a halt.

## Footnotes
[^1]: Even with SSDs, disrupting sequential reads decreases overall performance
