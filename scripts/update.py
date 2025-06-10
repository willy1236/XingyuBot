import os
import time

import git


def update_repository():
	print("[Update Module] Start")
	try:
		current_dir = os.path.dirname(os.path.abspath(__file__))
		location = os.path.dirname(current_dir)

		repo = git.Repo(location)
		pull_info = repo.remotes.origin.pull()

		if pull_info:
			if pull_info[0].flags & pull_info[0].HEAD_UPTODATE:
				print("[Update Module] Already up-to-date")
			else:
				for info in pull_info:
					if info.flags & info.FAST_FORWARD:
						print(f"Update: Fast-forward to {info.commit}")
					elif info.flags & info.FORCED_UPDATE:
						print(f"Update: Forced update to {info.commit}")
					else:
						print(f"Update: {info.note}")
				print("[Update Module] Update successful")
		else:
			print("[Update Module] No updates")

	except git.GitCommandError as git_error:
		print(f"[Update Module] Git operation error: {git_error}")
	except Exception as e:
		print(f"[Update Module] Error: {e}")

	print("[Update Module] Close after 3 seconds...")
	time.sleep(3)

if __name__ == "__main__":
    update_repository()
