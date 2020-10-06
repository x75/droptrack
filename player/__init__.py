import json

from multiprocessing import Pool
import threading

from os import getcwd, path
from time import time
from .collector import Collector
from .store import Store
from .player import PlayerError


config = {
    'server': 'tcp://127.0.0.1:5200',
    # 'webapp': 'http://194.13.80.137:5000',
    'webapp': 'http://soup.jetpack.cl/droptrack/',
    'req': 'tcp://127.0.0.1:5210',
    'tracks': path.join(getcwd(), 'data/download/'),
    'last_sync': './data/last_sync'
}

# if path.exists('server/config.json'):
#     with open('server/config.json', 'r') as configfile:
#         for key, value in json.load(configfile).items():
#             config[key] = value


def handler(track_url):
    store = Store(config)
    try:
        location = store.download(track_url)
    except PlayerError as e:
        print(e)
    else:
        store.queue_track(location)


def main():
    pool = Pool(processes=1)
    collector = Collector(config)
    collector.register_handler(handler)

    def callback(*args):
        print('callback', args)
    
    def backlog_req_func(*args, **kwargs):
        print('player.init backlog_req_func')
        if collector.request_backlog():
            collector.write_sync_time(time())
        else:
            print('backlog sync failed')

    thr = threading.Thread(target=backlog_req_func, args=(), kwargs={})
    thr.start() # Will run "foo"
    # backlog_req = pool.apply_async(backlog_req_func, [], callback=callback)
    
    collector.run()
