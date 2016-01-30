# coding: utf-8
import threading
from redis import Redis
from redis.sentinel import Sentinel


class NginxManager(threading.Thread):
    def __init__(self, r, channels):
        super(self.__class__, self).__init__()
        self.redis = r
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(channels)

    def run(self):
        for self.item in self.pubsub.listen():
            if self.item['data'] == "KILL":
                self.pubsub.unsubscribe()
                print self, "Unsubscribed and finished."
                break
            else:
                self.work()

    def work(self):
        if self.should_make_config:
            self._make_config()
        elif self.should_reload:
            self._reload()
        elif self.should_restart:
            self._restart()
        else:
            print 'Channel Message has to be {}'.format(
                ['restart', 'reload', 'make_config', 'maintenance_on', 'maintenance_off',]
            )

    @property
    def should_make_config(self):
        if "make_config" == self.item['data']:
            return True
        return False

    @property
    def should_restart(self):
        if "restart" == self.item['data']:
            return True
        return False

    def _restart(self):
        print 'restart'

    @property
    def should_reload(self):
        if "reload" == self.item['data']:
            return True
        return False

    def _make_config(self):
        print 'make_config'

    def _reload(self):
        print 'reload'


if __name__ == "__main__":
    r = Redis()
    nginx_manager = NginxManager(r, ['REDIS_PUBSUB_CHANNEL'])
    nginx_manager.start()
