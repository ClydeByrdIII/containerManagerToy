#!/usr/bin/env python3
import os
import signal

from typing import List, Set

""" Various utilities to manage namespaces and cgroups """


def recursivelyDeleteCgroups(cgroupPath: os.PathLike) -> None:
    """
    Delete leaf nodes before parents
    Ignore the files in the directories
    they can't actually be removed due to cgroupfs semantics
    """
    for root, dirs, _ in os.walk(cgroupPath, topdown=False):
        # remove all the leafs first
        for d in dirs:
            os.rmdir(os.path.join(root, d))
        # remove the root directory
        os.rmdir(root)


def getCurrentCgroup():
    """
    Grab the calling process' cgroup
    see https://man7.org/linux/man-pages/man7/cgroups.7.html for format
    NOTE: This only cgroup v2 is supported
    NOTE: We also assume /sys/fs/cgroup is the mount point for cgroupfs
    """
    with open(f"/proc/self/cgroup", "r") as f:
        cgroupEntry = f.readline()
        _, _, relCgroupPath = cgroupEntry.split(":")
        return os.path.join("/sys/fs/cgroup", relCgroupPath.lstrip("/").rstrip())


def getPidsFromCgroup(cgroupPath: os.PathLike) -> Set[int]:
    """
    Get every pid belonging to the given cgroup

    The cgroup.procs file can be read to obtain a list of the
    processes that are members of a cgroup.  The returned list of
    PIDs is not guaranteed to be in order.  Nor is it guaranteed to
    be free of duplicates.  (For example, a PID may be recycled while
    reading from the list.)
    see https://man7.org/linux/man-pages/man7/cgroups.7.html for more
    """
    pids = set()
    filename = os.path.join(cgroupPath, "cgroup.procs")
    with open(filename, "r") as f:
        # for every line in cgroup.procs, convert to int and store
        for line in f.readlines():
            pids.add(int(line))
    return pids


def sendSignalToCgroup(
    cgroupPath: os.PathLike, sig: signal.Signals, pidsToIgnore: List[int] = None
) -> None:
    """
    Send the given signal to all processes in the given cgroup, except for
    the calling process (if it's in the cgroup) and the given ignore set
    NOTE: This is a best effort call. Technically it does not handle fork
    bombs. Freezing the cgroup first, systemctl kill, or killall5 type of solutions
    would be a better way to go about it
    e.g https://github.com/systemd/systemd/blob/bf1886226724b3db0779d643195d428575cff0be/src/basic/cgroup-util.c#L250
    or
    https://github.com/limingth/sysvinit/blob/master/sysvinit-2.88dsf/src/killall5.c#L1063
    """
    pids = getPidsFromCgroup(cgroupPath)
    # don't send a signal to ourselves
    pids.discard(os.getpid())

    # ignore whatever else requested
    if pidsToIgnore:
        for pid in pidsToIgnore:
            pids.discard(pid)

    for pid in pids:
        # send signal to the rest
        os.kill(pid, sig)


def generateUnshareCommand(
    cmd: List[str], usePidNs: bool = False, isContainer: bool = False
) -> List[str]:
    """
    Generate an unshare(1) command (which is based on unshare(2) system call)
    This command can be used as a shim to move the invoking processes in to
    new namespaces.
    This is valuable when access to clone(2) is not easy

    We always provide --mount, because Assistent manager nor container mounting
    should affect root namespace
    """

    command = ["/usr/bin/unshare", "--mount"]
    if usePidNs or isContainer:
        # If want to execute in new pid namespace, unshare will need to fork
        # as it's not really easy to make a pid ns without starting a new process
        command.extend(["--pid", "--fork", "--mount-proc"])
    if isContainer:
        # we likely want this new process to be isolated from the root namespace
        # so isolate more resources
        command.extend(["--ipc", "--uts", "--cgroup"])
    command.extend(cmd)
    return command
