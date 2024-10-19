import os
import time

import git


def update_repository():
    print('[更新模組] 開始')
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        location = os.path.dirname(current_dir)
        
        repo = git.Repo(location)
        pull_info = repo.remotes.origin.pull()
        
        for info in pull_info:
            print(f'更新：{info.note}')
        
        print('[更新模組] 更新成功')
    except git.GitCommandError as git_error:
        print(f'[更新模組] Git 操作錯誤：{git_error}')
    except Exception as e:
        print(f'[更新模組] 發生錯誤：{e}')

    print('[更新模組] 3秒後關閉...')
    time.sleep(3)

if __name__ == "__main__":
    update_repository()
