
from common import util, multicast

class LedControl(util.Threadbase):
    def __init__(self, configuration):
        super(Client, self).__init__(name='client')