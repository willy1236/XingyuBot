import time
import os

# https://github.com/gitpython-developers/GitPython
import git


print('[更新模組] Start')
try:
    location = os.path.dirname(os.path.abspath(__file__))
    g = git.cmd.Git(location)
    msg = g.pull()
    print(msg)
except Exception as e:
    print('[更新模組] A error occurred.')
    print(e)

print('[更新模組] Close in 3 seconds...')
time.sleep(3)
exit()