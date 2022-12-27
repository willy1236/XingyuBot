# https://github.com/gitpython-developers/GitPython
import git,json,time,os

# with open('database/setting.json','r') as jfile:
#     dict = json.load(jfile)
#     location = dict.get('location')

#if location:
location = os.path.dirname(os.path.abspath(__file__))
g = git.cmd.Git(location)
msg = g.pull()
print(msg)

# else:
#     print("Location not found.")

print('Close in 3 seconds...')
time.sleep(3)