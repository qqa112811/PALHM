# PALHM JSON Config Format
PALHM is configured with JSON documents. PALHM supports the original JSON and
JSONC(the JSON with comments). PALHM handles jsonc documents by converting
them to json by an external command. PALHM distinguishes between these two
format by the file name extension. The conversion only occurs when the name of
the config file ends with `.jsonc`.

To support the IEEE754 infinity, the data types used for some values are both
string and number. The former will be parsed by the relevant type class before
they are processed.

## Structure
The format of the object feature table.

| ATTR | MEANING |
| - | - |
| Key | The key string of the object |
| Value | The value of the object |
| Required | Whether the object is required as the member of the parent object |
| Include | Include behaviour. "MERGE" or "OVERRIDE" |
| Range | Range of the value if NUMERICAL |

### include
| ATTR | DESC |
| - | - |
| Key | "include" |
| Value | ARRAY of STRINGs |
| Required | NO |
| Include | MERGE |

```jsonc
{
  "include": [ "/etc/palhm/conf.d/core.json" ]
}
```

The array is the list of paths to other config files to include in the current
config. The config files in the array are merged into the config. No two exec
definitions or task with the same id can exist in included config files. The
global settings such as "vl" and "nb-workers" will be silently overridden if
they are defined in the subsequent config files. Absolute or relative paths can
be used. The relative paths are resolved in the same manner as the `#include`
preprocessor in C: if used in the config file passed to PALHM via the `-f`
option, the paths will be resolved from the current working directory of the
process. Otherwise(if used in the subsequent includes), the paths will be
resolved from the directory of the current config file. A config file cannot be
included twice as PALHM detects circular inclusion by keeping track of the
included config files.

### modules
| ATTR | DESC |
| - | - |
| Key | "modules" |
| Value | ARRAY of STRINGs |
| Required | NO |
| Include | MERGE |

The array is the list of PALHM modules to import. Run `palhm mods` for the
list of modules installed on the system.

```jsonc
{
  "modules": [ "aws" ]
}
```

### nb-workers
| ATTR | DESC |
| - | - |
| Key | "nb-workers" |
| Value | INTEGER |
| Required | NO |
| Include | OVERRIDE |
| Range | (-inf, inf) |

```jsonc
{
  /* The number of threads the process is restricted to. Usually same as
   * $(nproc)
   */
  "nb-workers": 0,
  // Use Python default
  "nb-workers": -1,
  // No concurrency
  "nb-workers": 1
}
```

The number of maximum worker threads. Use a negative integer to use the Python
default value(see
[ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor)).
Use zero to set it to the number of threads the process is allowed to
utilise(see [os.sched_getaffinity()](https://docs.python.org/3/library/os.html?highlight=sched_getaffinity#os.sched_getaffinity)).
Use a positive integer to restrict the number of worker threads.

### vl
| ATTR | DESC |
| - | - |
| Key | "vl" |
| Value | INTEGER |
| Required | NO |
| Include | OVERRIDE |
| Range | (-inf, inf) |

```jsonc
{
  "vl": 0, // CRITICAL
  "vl": 1, // ERROR
  "vl": 2, // WARNING
  "vl": 3, // INFO
  "vl": 4, // DEBUG + 0
  "vl": 5, // DEBUG + 1
  "vl": 6  // DEBUG + 2
  /* ... */
}
```

The verbosity level, the higher the more verbose.The value is translated from
PALHM's "the higher the more verbose" scheme to Python's [logging facility
logging level](https://docs.python.org/3/library/logging.html#logging-levels).
Defaults to 3.

You don't really need this. THe best practice is using the default value for the
config and using the `-q` option for a crond or timer unit. When debugging info
is required, simply increase the verbosity with the `-v` option.

### Execs
| ATTR | DESC |
| - | - |
| Key | "execs" |
| Value | ARRAY of [Exec Definition Object](#exec-definition-object)s |
| Required | NO |
| Include | MERGE |

#### Exec Definition Object
* "id": id string **(required)**
* "argv": argument vector **(required)**
* "env": additional environment variable mapping. The value must be an object
  whose members are string to string mapping. The key represents the name of the
  variable and the value the value of the variable.
* "ec": valid exit code range. Defaults to "==0"
  * Inclusive range format: &lt;MIN&gt;-&lt;MAX&gt;
  * Comparator format: \[C\]&lt;N&gt;
  * Where
    * MIN: minimum inclusive valid exit code
    * MAX: maximum inclusive valid exit code
    * N: integer for comparison
    * C: comparator. One of &lt;, &lt;=, &gt;, &gt;= or ==. Defaults to ==
  * Examples
    * ">=0": ignore exit code(always success)
    * "<2" or "0-1": accept exit code 0 and 1
    * "1": accept exit code 1 only
 * "vl-stderr": verbosity level of stderr from the process. Defaults to 1
 * "vl-stdout": verbosity level of stdout from the process. Defaults to 3

 Note that stdout and stderr from the process are not passed to the logger.
 "vl-stderr" and "vl-stdout" are merely used to determine whether the outputs
 from the process have to be redirected to `/dev/null` or the stdio of the PALHM
 process.

```jsonc
{
  "id": "pgp-enc",
  "argv": [ "/bin/pgp", "-e", "-r", "backup", "--compress-algo", "none" ],
  "env": {
    "LC_ALL": "C",
    "GNUPGHOME": "~/gnupg"
  },
  "ec": "==0",
  "vl-stderr": 1,
  "vl-stdout": 3
}
```

### Tasks
| ATTR | DESC |
| - | - |
| Key | "tasks" |
| Value | ARRAY of OBJECTs |
| Required | NO |
| Include | MERGE |

#### Predefined Pipeline Exec Object
* "type": "exec" **(REQUIRED)**
* "exec-id": id of the Exec Definition Object **(REQUIRED)**

```jsonc
{
  "type": "exec",
  "exec-id": "filter-zstd-parallel"
}
```

#### Appended Pipeline Exec Object
* "type": "exec-inline" **(REQUIRED)**
* "exec-id": id of the Exec Definition Object **(REQUIRED)**
* "argv": array of string, which is the argument vector to append **(REQUIRED)**
* "env": environment variable mapping object. See [#Exec Definition
  Object](#exec-definition-object)

```jsonc
{
  "type": "exec-append",
  "exec-id": "tar",
  "argv": [ "-C", "/", "etc", "home", "root", "var" ],
  "env": { "LC_ALL": "C" }
}
```

#### Inline Pipeline Exec Object
Same as [#Exec Definition Object](#exec-definition-object), except that this
object does not require the "id" member.

```jsonc
{
  "type": "exec-inline",
  "argv": [ "/bin/dnf", "--refresh", "-yq", "update" ]
}
```

#### Backup Task Definition Object
* "id": id string **(REQUIRED)**
* "type": "backup" **(REQUIRED)**
* "backend": see [README.md#Backend-param](../README.md#Backend-param)
  **(REQUIRED)**
* "backend-param": see [README.md#Backend-param](../README.md#Backend-param)
* "object-groups": array of [Backup Object Group Definition
  Objects](#backup-object-group-definition-object)
* "objects": array of [Backup Object Definition
  Objects](#backup-object-definition-object)

```jsonc
{
  "id": "root-backup",
  "type": "backup",
  "backend": "null",
  "backend-param": { /* ... */ },
  "object-groups": { /* ... */ },
  "objects": [ /* ... */ ]
}
```

##### Backup Object Group Definition Object
* "id": id string. Valid within the backup task **(REQUIRED)**
* "depends": array of other object group id strings on which the object group is
  dependent. The other groups must appear before the group definition.

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

##### Backup Object Definition Object
* "path": path to the backup output on the backend **(REQUIRED)**
* "alloc-size": the expected size of the object in bytes
* "group": the id of a [Backup Object Group Definition
  Object](#backup-object-group-definition-object)
* "pipeline": array of
  * [Predefined Pipeline Exec Objects](#predefined-pipeline-exec-object)
  * [Appended Pipeline Exec Objects](#appended-pipeline-exec-object)
  * [Inline Pipeline Exec Objects](#inline-pipeline-exec-object)

```jsonc
{
  "path": "srv.tar.zstd",
  "alloc-size": 2097152,
  "group": "tar-1",
  "pipeline": [
    {
      "type": "exec-append",
      "exec-id": "tar",
      "argv": [ "-C", "/", "srv" ]
    },
    { "type": "exec", "exec-id": "filter-zstd-parallel" }
  ]
}
```

A set of child processes for the backup ouput file will be created using the
Exec objects in the array.

The PALHM process waits for any of the child process in the pipeline. The exit
codes returned from the child processes will be tested as they exits one by one.
If PALHM encounters a child process returns an exit code that does not fall into
the acceptable exit code range, it will roll back the current copy of backup
before raising the exception. In this case, the exit code from the rest of child
processes are not processed[^1].

#### Routine Task Definition Object
* "id": id string **(REQUIRED)**
* "type": "routine" **(REQUIRED)**
* "routine": array of the id strings of
  * [Predefined Pipeline Exec Objects](#predefined-pipeline-exec-object)
  * [Appended Pipeline Exec Objects](#appended-pipeline-exec-object)
  * [Inline Pipeline Exec Objects](#inline-pipeline-exec-object)
  * [Builtin Function Objects](#builtin-function-object)
  * [Task Pointer Objects](#task-pointer-object)

```jsonc
[
  {
    "id": "update",
    "type": "routine",
    "routine": [
      {
        "type": "exec-inline",
        "argv": [ "/bin/dnf", "--refresh", "-yq", "update" ]
      },
      {
        "type": "exec-inline",
        "argv": [ "/bin/sa-update" ]
      }
    ]
  },
  {
    "id": "reboot",
    "type": "routine",
    "routine": [
      {
        "type": "builtin",
        "builtin-id": "sigmask",
        "param": [ { "action": "block", "sig": [ "INT", "TERM" ] } ]
      },
      {
        "type": "exec-inline",
        "argv": [ "/sbin/reboot" ]
      }
    ]
  },
  {
    "id": "default",
    "type": "routine",
    "routine": [
      { "type": "task", "task-id": "update" },
      { "type": "task", "task-id": "reboot" }
    ]
  }
]
```

##### Task Pointer Object
* "type": "task"
* "task-id": id string of
  * [Backup Task Definition Object](#backup-task-definition-object)
  * [Routine Task Definition Object](#routine-task-definition-object)

##### Builtin Function Object
* "type": "builtin"
* "builtin-id": "sigmask"
* "param": function-specific param object
  * [sigmask Builtin Function Param](#sigmask-builtin-function-param)

##### sigmask Builtin Function Param
The sigmask builtin function is the direct interface to
[pthread_sigmask()](https://docs.python.org/3/library/signal.html?highlight=sigmask#signal.pthread_sigmask).
Run `kill -l` for valid signals on your system. This builtin function can only
be used on Unix systems.

* "action": "block" or "unblock"
* "sig": array of signal strings. A numberic value and the name of a signal with
  or without "SIG" prefix are accepted. Valid values include "TERM", "SIGTERM",
  15, "INT", "SIGINT" and "2"

### boot-report
| ATTR | DESC |
| - | - |
| Key | "boot-report" |
| Required | NO |
| Include | MERGE except "mua" |

The contents of the mail is in yaml format. The entirety of the body can be fed
into a yaml parser for machine processing. The "header" attribute defines the
header contents of the yaml document for humans.

* "mua": mail user agent(MUA) front-end. Can only be specified once throughout
  the config files **(required)**
  * "stdout": prints the contents of the mail to stdout. Does not actually send
    mail. The "mail-to" attribute is not used. For testing
  * "mailx": use the mailx command to send mail
  * "aws-sns": use AWS SNS to send messages
* "mua-param": parametres for AWS SNS client. See
  [README.md##aws-sns-mua](../README.md#aws-sns-mua)
* "mail-to": array of boot report mail recipients. The values must be
  recognisable by the MUA **(required)**
* "subject": title for mail. [Content Substitution
  Variables](#content-substitution-variables) can be used
* "header": header content in mail body. The header is transformed to yaml
  comments and prepended to the start of the yaml document. [Content
  Substitution Variables](#content-substitution-variables) can be used
* "uptime-since": include output of `uptime --since`
* "uptime": include output of `uptime -p`
* "bootid": include boot_id(`/proc/sys/kernel/random/boot_id`)
* "boot-wait": boot wait backend
  * "systemd": wait for systemd to finish boot up
* "delay": the number of seconds to wait before sending mail. Finite float equal
   to or greater than zero

#### Content Substitution Variables
* {hostname}: The hostname. See
  [platform.node()](https://docs.python.org/3/library/platform.html#platform.node)

## Footnotes
[^1]: they're most likely 141(terminated by SIGPIPE)
