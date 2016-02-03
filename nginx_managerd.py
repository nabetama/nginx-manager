# coding: utf-8
import os
import threading
from jinja2 import Environment, FileSystemLoader
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
            if "KILL" == self.item['data']:
                self.pubsub.unsubscribe()
                print self, "Unsubscribed and finished."
                break
            else:
                self.work()

    def work(self):
        print 'Channel Message has to be {}'.format(
            ['restart', 'reload', 'make_config', 'maintenance_on', 'maintenance_off',]
        )

if __name__ == "__main__":
    r = Redis()
    nginx_manager = NginxManager(r, ['PUBSUB_CHANNEL'])
    nginx_manager.start()
