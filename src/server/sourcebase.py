from common import util


class SourceBase(util.Threadbase):
    def __init__(self, name):
        super(SourceBase, self).__init__(name=name)
        self.pipeline = None

    def send_event(self, key, value):
        self.emit('event', {'name': self.name, 'key': key, 'value': value})
