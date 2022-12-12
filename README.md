This is an education project for those that are interested in container manager
fundamentals.

## Testing

### State Machine Tests
```
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

