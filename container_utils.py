#!/usr/bin/env python3
import os
import signal
from typing import List, Set

""" Various utilities to managed namespaces and cgroups """
def recursivelyDeleteCgroups(cgroupPath: os.PathLike) -> None:
    """
    Delete leaf nodes before parents and we want to ignore the files
    in the directories as they can be ignored for removal     
    """
    for root, dirs, _ in os.walk(cgroupPath, topdown=False):
        # remove all the leafs first
        for d in dirs:
            os.rmdir(os.path.join(root, d))
        # remove the root directory
        os.rmdir(root)

def getCurrentCgroup():
    with open(f"/proc/self/cgroup", "r") as f:
        cgroupEntry = f.readline()
        _, _, relCgroupPath = cgroupEntry.split(":")
        return os.path.join("/sys/fs/cgroup", relCgroupPath.lstrip("/").rstrip())

def getPidsFromCgroup(cgroupPath: os.PathLike) -> Set[int]:
    pids = set()
    filename = os.path.join(cgroupPath, "cgroup.procs")
    with open(filename, "r") as f:
        # for every line in cgroup.procs, convert to int and store
        for line in f.readlines():
            pids.add(int(line))
    return pids

def sendSignalToCgroup(cgroupPath: os.PathLike, sig: signal.Signals, pidsToIgnore: List[int]=None) -> None:
    pids = getPidsFromCgroup(cgroupPath)
    # don't want to send signal to ourselves
    pids.discard(os.getpid())
    
    # ignore whatever else requested
    if pidsToIgnore:
        for pid in pidsToIgnore:
            pids.discard(pid)
    
    for pid in pids:
        # send signal to the rest
        os.kill(pid, sig)
        
def generateUnshareCommand(cmd: List[str], usePidNs: bool = False, isContainer: bool = False) -> List[str]:
    """ 
    Generate an unshare(1) command (which is based on unshare(2) system call)
    this command can be used as a shim to move the invoking processes in to 
    new namespaces.
    This is valuable when access to clone(2) is not easy
    
    We always provide --mount, because Assistent manager nor container mounting 
    should affect root root namespace
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