import subprocess
from common.log import logger as log
from common import util


class CECAudio(util.Threadbase):  # missing terminate (incl timeout on read)
    def __init__(self, callback):
        super(CECAudio, self).__init__(name='cecaudio')
        self.callback = callback
        self.start()

    def terminate(self):
        super().terminate()
        self.p.kill()

    def run(self):
        # this will (most likely) disable the internal tv speakers and send audio on
        try:
            self.p = subprocess.Popen('cec-client -t a'.split(), stdout=subprocess.PIPE)
        except FileNotFoundError:
            util.die('unable to start cec-client (is libcec installed?)', 1, True)

        log.info('cec-client started')

        while self.p.poll() is None:
            out = self.p.stdout.read(1000)
            print(str(out))
            if '05:44:41'.encode() in out:
                self.callback('vol_up')
            elif '05:44:42'.encode() in out:
                self.callback('vol_down')
            elif '05:44:43'.encode() in out:
                self.callback('mute')

        log.info('cec listener exits')
