import os
import subprocess
import threading
import time

from starlib import log


class BaseThread(threading.Thread):
    def __init__(self, name):
        super().__init__(name=name)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

class ltThread(BaseThread):
    def __init__(self):
        super().__init__(name='ltThread')

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting ltThread")
            os.system('lt --port 14000 --subdomain starbot --max-sockets 10 --local-host 127.0.0.1 --max-https-sockets 86395')
            #cmd = [ "cmd","/c",'lt', '--port', '14000', '--subdomain', 'willy1236', '--max-sockets', '10', '--local-host', '127.0.0.1', '--max-https-sockets', '86395']
            #cmd = ["cmd","/c","echo", "Hello, World!"]
            #self.process = psutil.Popen(cmd)
            #self.process.wait()
            log.info("Finished ltThread")
            time.sleep(5)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

        print("ltThread stopped")

class ServeoThread(BaseThread):
    def __init__(self):
        super().__init__(name='ServeoThread')

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting ServeoThread")
            os.system("ssh -R star1016:80:127.0.0.1:14000 -R startwitch:80:127.0.0.1:14001 serveo.net")
            time.sleep(60)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

class LoopholeThread(BaseThread):
    def __init__(self):
        super().__init__(name='LoopholeThread')

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting LoopholeThread")
            result = subprocess.run(["loophole", "http", "14000", "127.0.0.1", "--hostname", "cloudfoam"], capture_output=True, text=True)
            log.info(f'Stdout: {result.stdout}')
            log.info(f'Stderr: {result.stderr}')
            log.info(f'Exit status: {result.returncode}')
            time.sleep(30)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

class LoopholeTwitchThread(BaseThread):
    def __init__(self):
        super().__init__(name='LoopholeTwitchThread')

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info("Starting LoopholeTwitchThread")
            result = subprocess.run(["loophole", "http", "14001", "127.0.0.1", "--hostname", "twitchcloudfoam"], capture_output=True, text=True)
            log.info(f'Stdout: {result.stdout}')
            log.info(f'Stderr: {result.stderr}')
            log.info(f'Exit status: {result.returncode}')
            time.sleep(30)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()