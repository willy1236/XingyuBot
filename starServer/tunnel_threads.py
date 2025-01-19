import os
import subprocess
import time

from starlib import BaseThread, log, Jsondb


class ltThread(BaseThread):
    def __init__(self):
        super().__init__(name='ltThread')

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.info(f"Starting {self.name}")
            os.system('lt --port 14000 --subdomain starbot --max-sockets 10 --local-host 127.0.0.1 --max-https-sockets 86395')
            #cmd = [ "cmd","/c",'lt', '--port', '14000', '--subdomain', 'willy1236', '--max-sockets', '10', '--local-host', '127.0.0.1', '--max-https-sockets', '86395']
            #cmd = ["cmd","/c","echo", "Hello, World!"]
            #self.process = psutil.Popen(cmd)
            #self.process.wait()
            log.info(f"Finished {self.name}")
            time.sleep(5)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

        print(f"{self.name} stopped")

class ServeoThread(BaseThread):
    def __init__(self):
        super().__init__(name='ServeoThread')

    def run(self):
        reconnection_times = 0
        while not self._stop_event.is_set():
            log.debug(f"Starting {self.name} {reconnection_times}")
            #result = subprocess.run(["ssh", "-R", "cloudfoam:80:127.0.0.1:14000", "-R", "cloudfoamtwitch:80:127.0.0.1:14001", "serveo.net"], capture_output=True, text=True)
            result = subprocess.run(["ssh", "-R", "yunmo:80:127.0.0.1:14000", "serveo.net"], capture_output=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log.debug(f'Stdout: {result.stdout}')
            log.debug(f'Stderr: {result.stderr}')
            log.debug(f'Exit status: {result.returncode}')
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
            log.debug(f"Starting {self.name} {reconnection_times}")
            result = subprocess.run(["loophole", "http", "14000", "127.0.0.1", "--hostname", "cloudfoam"], capture_output=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log.debug(f'Stdout: {result.stdout}')
            log.debug(f'Stderr: {result.stderr}')
            log.debug(f'Exit status: {result.returncode}')
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
            log.info(f"Starting {self.name} {reconnection_times}")
            result = subprocess.run(["loophole", "http", "14001", "127.0.0.1", "--hostname", "twitchcloudfoam"], capture_output=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log.debug(f'Stdout: {result.stdout}')
            log.debug(f'Stderr: {result.stderr}')
            log.debug(f'Exit status: {result.returncode}')
            time.sleep(30)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()

class NgrokTwitchThread(BaseThread):
    def __init__(self):
        super().__init__(name='NgrokTwitchThread')

    def run(self):
        reconnection_times = 0
        callback_url = Jsondb.get_token('twitch_chatbot')['callback_uri'].split('://')[1]
        while not self._stop_event.is_set():
            log.info(f"Starting {self.name} {reconnection_times}")
            result = subprocess.run(["ngrok", "http", f"--url={callback_url}", "14001"], capture_output=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log.debug(f'Stdout: {result.stdout}')
            log.debug(f'Stderr: {result.stderr}')
            log.debug(f'Exit status: {result.returncode}')
            time.sleep(30)
            reconnection_times += 1
            if reconnection_times >= 5:
                self._stop_event.set()