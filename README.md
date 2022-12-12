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

This is no means official, but I like to think of the container manager as three classes of entities, the state machine, the executor, and the assistent manager. I'd say there's typically one state machine, and one or more of each an executor and assistent manager.

![entities](https://user-images.githubusercontent.com/1676822/206999566-da8fa727-156c-4cf9-beb1-e3e1baf743a2.png)


### The State Machine

Just like systemd units or Linux processes, containers too can be in a finite amount of states. How many and which states is an implementation detail.
Check out [solaris zone states](https://en.wikipedia.org/wiki/Solaris_Containers) for a real example.

We wrap our state machine in a (thrift) server. The server itself only concerns itself with maintaining metadata around containers and their lifetimes.

In our implementation we support the following state definitions:
* READY: A container can be "ready" to be run (aka runnable) meaning the container manager has prepared everything for the container to be invoked
* RUNNING: A container is currently running
* STOPPING: A container is in the process of shutting down
* DEAD: A container has exited or was killed by a signal
* LOST: A container's status is unknown

The state machine transitions can be modeled like so:

![state_machine](https://user-images.githubusercontent.com/1676822/206984191-5c827f10-ea0c-4d61-9fa0-4d85920c1f42.png)

### The Executor

Is simply one or more threads of execution doing the deferred work that the state machine can't or shouldn't do itself.
We want the server/state machine to be fast, so the server should just queue work up for the executor to do. Not unlike the top and bottom half of linux interrupt handlers.

In our implementation we have the executor perform container preparations, cgroup manipulation, fork/execing.
The executor could be local threads or even another process, heck with some elbow grease, systemd could perform the duties of an executor.

### The Assistent Manager

In the industry this is called the [shim](https://github.com/containerd/containerd/blob/main/runtime/v2/README.md). The container manager may supervise all containers, but even managers sometimes have assistents that make sure everything is running smoothly, when the manager isn't around.

This is one of the purposes of the assistent manager. It will onboard (start) the container in to the right cgroups, privileges, starting point, etc.
It will live even when the container manager is dead or temporarily missing. It can report to the manager the status of the container. It can stop the container when requested by the manager and so much more that the container manager itself can't or shouldn't do.

## Implementation

For this project there were some design decisions at play that greatly influences the system.
Surprisingly the language is not the biggest issue (although it caused some inconviences).

Here is the big picture

![entities](https://user-images.githubusercontent.com/1676822/207086317-8e4baf17-bca0-486f-9cad-f0671f7a8d7e.png)

### 1 ) The desire to get something correct and running 
This played the biggest part. In the ensuing mini-sections I'll detail where this applied.

### 2) Python was the chosen language
Honestly, I'd have preferred to write this in c++, rust, or go in that order.
However, in my experience, the state machine is not often the bottle neck in container management.
Python was much quicker to implement and iterate on, while requiring the least set up overhead.
The current feature set of all three entities are minimal enough, where choosing python only adds annoyance to some house keeping duties
when one can't find python bindings for certain system calls like clone(2). While not impossible to use these system calls in python, they're much more cumbersome than a language like c/c++/rust.

### 3) The API server is single threaded

Thrift's Simple TServer implementation has a single thread for connections and processing.
This means only one client can connect at a time. 
This is great for showing how transitions in state are made and what makes the transitions at what times.
However it is rather annoying since it requires the multiple entities to be cooperative and not block each other inadvertently, which is something you can't guarantee in practice.

Given more time, I would make a multi-threaded/process state machine that is thread/async-safe to avoid such problems.

For now every client must close the connection after their call in order for the other entities to progress the state machine.

### 4) These are application containers

This means that it's the responsibility of the user to supply commands that will probably handle signals.
Due to containers running in their own pid namespace, their command will run as pid 1 in that namespace, meaning it will by default ignore all signals.
The user will need code to explicitly re-instate signals for it to be able to gracefully shutdown.

This is a common problem in docker, solved in various ways, one of which is [dumb-init](https://engineeringblog.yelp.com/2016/01/dumb-init-an-init-for-docker.html)

### 5) The state machine only does what it's told

Rather than having a very active server that tries to do many things, such as actively preparing the filesystem or outward connections to assistent managers, we keep it as dumb as possible.

State transitions must be enacted, by some outside entity such as a client, executor, or assistent manager. This means in the abscence of an entity 
making requests to transistion states, the state machine will do nothing.

This is an important trade off when it comes to having a scheduler manage the container manager. You don't want the container manager making too many local decisions, as it can ruin the state in the scheduler (or whatever controlling entity).

### 6) Push vs Pull

The tradeoffs of a push vs pull architecture in monitoring are [well discussed](https://blog.sflow.com/2012/08/push-vs-pull.html), so I won't go too deep in to it.

We choose to have assistent managers report to the singular container manager rather than the container manager polling the assistent managers.
This allows assistent managers to know relatively quickly if they've gone rogue / LOST.

### 7) File system isolation is not supported

Due to a lack of time, file system isolation using chroot(2) / pivot-root(2) / mount (2) MS_MOVE was not implemented, but could be done simply using
a cached os tree (like alpine linux or some minimal distribution), creating a unique root tree for each container, copying the os tree to each root, and then pivot rooting the container to that root tree. Similar to what I did in my slides.

### 8) Container metadata is not persisted across restarts

A container manager should be robust and have the ability to recover state on recovery/restart.
Even in situations where all the state is wiped, it could be beneficial for the container manager to detect rogue containers and clean them up.
In our implementation we deferred persisting metadata due to time, but we did implement a mechanism for assistent managers to ABORT when not recognized by the container manager

### 9) Nothing initiates LOST state transitions (yet)

Due to time, LOST state transitioning was not implemented. There's many reasons for a assistent manager to go unresponsive. Detecting such cases is the responsibility of the executor, since the assistent can't do so on it's own (otherwise it wouldn't be LOST).

### 10) There is one thrift handler for all entities

The scheduler, executor, and assistent manager all use different thrift calls. And for the latter 2, they should use unix domain sockets for communication since they should all be local. They're currently one handler and TCP sockets because of time.

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

