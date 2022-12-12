This is an education project for those that are interested in container manager.

## Background
I used to give a talk to students ([found here](https://docs.google.com/presentation/d/1pv8o65pQTUE-bvnULzowHRxilorK5vz0/edit?usp=sharing&ouid=108648618764137259019&rtpof=true&sd=true)) about creating your own container manager.

It attempted to break down what a container is at its core.
The industry at large tries to provide a concept of containers that is really a high level abstraction that can be hard to grasp.
Unlike kernels like solaris, which have [kernel-level abstractions](https://en.wikipedia.org/wiki/Solaris_Containers) in their kernel that define a container, the Linux kernel is not one of them.

This is what can be hard when trying to choose and understand the various container runtimes that exist today. What one runtime might think is essential, another might think is an optional feature.

Generally, on Linux kernels, a container is basically one or more Linux processes, isolated in one or more Linux namespaces, limited/partitioned by Linux cgroups. I personally, like to consider the usage of one or more Linux capabilities in that description too, but I might be in the minority.

Notice how image construction is not listed in those components. That's usually a higher level concept. The industry likes to include the constructed, immutable image as part of the container abstraction. At a primitive level though, the Linux kernel does not care.

If you didn't get a chance to check out my slides linked earlier:

#### process:

an instance of a running program/binary.

#### [namespace](https://man7.org/linux/man-pages/man7/namespaces.7.html):
namespace wraps a global system resource in an abstraction that
makes it appear to the processes within the namespace that they
have their own isolated instance of the global resource.  Changes
to the global resource are visible to other processes that are
members of the namespace, but are invisible to other processes.

#### [cgroup](https://man7.org/linux/man-pages/man7/cgroups.7.html):
Control groups, usually referred to as cgroups, are a Linux
kernel feature which allow processes to be organized into
hierarchical groups whose usage of various types of resources can
then be limited and monitored.

#### [capability](https://man7.org/linux/man-pages/man7/capabilities.7.html):
Linux divides the privileges traditionally associated with superuser into distinct units,
known as capabilities, which can be independently enabled and
disabled.

## Container Managers

Now that you know what a Linux "container" is or could be, it will be easier to describe what a container manager is.
A Linux container manager is more or less a process manager, not too unlike your unix shell, local init system (sysvinit, systemd, upstartd).
It will create new processes, monitor the life time of processes, kill processes, and provide information about processes to some authority (e.g scheduler).

The industry likes to include image distribution as a responsibility of the container manager and I don't disagree, but for this toy we're focusing primarily on the process management fundamentals. So far now, we will skip the intracies of image construction, distribution, and even the more trivial chroot(2) / pivot_root(2) / mount(2) MS_MOVE system calls often used in moving a process in to its own filesystem view.

We will get back to the file system isolation system calls support in a later round of commits.

## Container Manager Building Blocks

This is no means official, but I like to think of the container manager as three entities, the state machine, the executor, and the assistent manager

### The State Machine

Just like systemd units or Linux processes, containers too can be in a finite amount of states. How many and which states is an implementation detail.
Check out [solaris zone states](https://en.wikipedia.org/wiki/Solaris_Containers) for a real example.

In our implementation we support the following state definitions:
* READY: A container can be "ready" to be run (aka runnable) meaning the container manager has prepared everything for the container to be invoked
* RUNNING: A container is currently running
* STOPPING: A container is in the process of shutting down
* DEAD: A container has exited or was killed by a signal
* LOST: A container's status is unknown

The state machine transitions can be modeled like so:

![state_machine](https://user-images.githubusercontent.com/1676822/206984191-5c827f10-ea0c-4d61-9fa0-4d85920c1f42.png)



## Testing

Tests were executed on a Debian 11 aarch64 (virtual machine) 
Testing environment:
```
# cat /etc/os-release 
PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"
NAME="Debian GNU/Linux"
VERSION_ID="11"
VERSION="11 (bullseye)"
VERSION_CODENAME=bullseye
ID=debian
HOME_URL="https://www.debian.org/"
SUPPORT_URL="https://www.debian.org/support"
BUG_REPORT_URL="https://bugs.debian.org/"
# uname -a
Linux debian 5.10.0-18-arm64 #1 SMP Debian 5.10.140-1 (2022-09-02) aarch64 GNU/Linux
```

## package requirements 
```
sudo apt-get install automake bison flex g++ git libboost-all-dev libevent-dev libssl-dev libtool make pkg-config
sudo apt-get install libthrift-dev thrift-compiler python3-thrift
```

## other requirements
container manager, executor, and assistent manager need to be ran as root since they're making various filesystem operations
and system calls. This isn't to say all container managers need root, but typically elevated privileges are needed depending
on the feature set desired.

### State Machine Tests
```
# generate the thrift code before executing any thing
thrift -r --gen py container_manager.thrift 
# the first test spawns it's own manager server
python3 state_machine_test.py
# the second test needs a manager server to be up already
python3 main.py &
# create 3 containers and exercise various life cycles
python3 lifecycle_test.py
```
The tests provided exercise the state machine
state_machine_test.py manually goes through all phases of the state machine without actually creating containers
lifecycle_test.py goes through the state machine while creating containers
This shows the basic flow of the API and container management is function

https://user-images.githubusercontent.com/1676822/206956929-42d5179d-5756-42b3-afb0-a4f78306fac7.mov

### Assistent Manager Abort Test
The following video shows that if our assistent manager reports to a container manager that does not
recognize it, the assistent manager is quick to kill the container workload and exit
This shows that rogue containers will take care of themselves if the container manager forgets about them
for some reason

https://user-images.githubusercontent.com/1676822/206957067-942a3e9f-e3fd-4124-b16e-7488dea8b379.mov

