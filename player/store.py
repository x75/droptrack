import json
import requests
import shutil
import os, glob
from os import path
from urllib.parse import urlparse
from subprocess import run, CalledProcessError
from .player import PlayerError

import hashlib
import acoustid
import chromaprint
# import soundfile as sf
import audioread
import numpy as np
import pandas as pd

from webapp.libdata import data_conf
from webapp.libdata import data_init, data_get_columns, data_get_index_next, data_append_row, data_write

def get_filefp(filepath):
    duration, fp_encoded = acoustid.fingerprint_file(filepath)
    fingerprint, version = chromaprint.decode_fingerprint(fp_encoded)
    return fingerprint

def get_filelength(filepath):
    # f = sf.SoundFile(filepath)
    # filelength = len(f) / f.samplerate

    with audioread.audio_open(filepath) as f:
        print(f.channels, f.samplerate, f.duration)
        filelength = f.duration
    return filelength

    
def get_filehash(filepath):
    # m = hashlib.md5()
    m = hashlib.sha256()
    with open(filepath, 'rb') as f: 
        for byte_block in iter(lambda: f.read(4096),b""):
            m.update(byte_block)
        # for chunk in iter(f.read(1024)):
        #     m.update(chunk)
        return m.hexdigest()
    return None

class Store(object):

    def __init__(self, config):
        self.trackstore_dir = config.get('tracks', '/tmp')
        webapp = config.get('webapp')
        if webapp:
            self.webapps = [webapp]
        else:
            self.webapps = config.get('webapps', [])

        # init track store
        # self.trackstore_filename = 'data/player_trackstore.csv'
        self.trackstore_filename = data_conf['trackstore_filename'] # 'data/player_trackstore_default.csv'
        self.trackstore_filename_base = data_conf['trackstore_filename_base'] 
        self.trackstore_key = 'miniclub6'
        self.ts = data_init(
            columns=data_conf['trackstore_columns'],
            filename=self.trackstore_filename)
        
        # try:
        #     self.ts = pd.read_csv(self.trackstore_filename)
        #     # self.trackstore = pd.HDFStore(self.trackstore_filename, mode='a')
        #     # self.ts = pd.read_hdf(self.trackstore_filename, self.trackstore_key)
        # except Exception as e:
        #     print('Could not load trackstore from file at {0}'.format(self.trackstore_filename))
        #     # continue without trackstore
        #     # self.trackstore = None
        #     # self.trackstore = pd.DataFrame(columns=['id', 'url', 'filename', 'filepath', 'length', 'fingerprint', 'hash'])
        #     self.ts = pd.DataFrame({'id': 0, 'url': 'none', 'filename': 'dummy', 'filepath': 'dummy', 'length': 0, 'fingerprint': '', 'hash': ''}, index=pd.Index([0]))
        #     self.ts.to_csv(self.trackstore_filename, index=False)
            
        # self.ts = self.trackstore[self.trackstore_key]

    def download(self, url, user_session=None):
        """player.Store.download
        """
        # print(f'player.store.download url {url}')
        # print('    from url {1} to self.trackstore_dir {0}'.format(self.trackstore_dir, url))
        if url.startswith('{'):
            url_dict = json.loads(url)
            url = url_dict['url']
            username = url_dict['username']
        else:
            username = 'default'
            
        components = urlparse(url)
        # print('    url components {0}'.format(components))


        # prepare trackinfo defaults
        filename = None
        filepath = None
        ytid = None
        ytaudiofmt = 'mp3'
        trkid = -1

        # try to get trackinfo from store
        trackinfo = self.ts[self.ts.url == url]
        print('    trackinfo length {0}'.format(len(trackinfo)))
        print('    trackinfo values {0}'.format(trackinfo.values))
        # print('player.store download trackinfo\n    \'{0}\''.format(trackinfo['filename'].tolist()[0]))
        
        # if track is in the store already
        if len(trackinfo) > 0:
            if len(trackinfo) > 1:
                trackinfo = list(trackinfo)[-1]
            
            # filename = str(trackinfo.filename.tolist()[0])
            # track is in the store and file does not exist
            trkid = int(trackinfo['id'].astype(object))
            filepath = str(trackinfo.filepath.tolist()[0])
            # print('    found filename {0}'.format(filename))
            # print('    found filepath {0}'.format(filepath))

            # filelength = str(trackinfo.length.tolist()[0])
            # filefp = str(trackinfo.fingerprint.tolist()[0])
            # filehash = str(trackinfo.hash.tolist()[0])

            # print(type(filelength), type(filefp), type(filehash))
            # # print(filelength == 'nan', filefp, filehash)
            # if filelength == 'nan':
            #     filelength = get_filelength(filepath)
            #     self.trackstore.loc[trackinfo.id]['filelength'] = filelength
            # if filefp == 'nan':
            #     filefp = get_filefp(filepath)
            #     self.trackstore.loc[trackinfo.id]['filefp'] = filefp
            # if filehash == 'nan':
            #     filehash = get_filehash(filepath)
            #     self.trackstore.loc[trackinfo.id]['filehash'] = filehash

            # self.trackstore.to_csv(self.trackstore_filename, index=False)
            
            # track is in the store and file exists            
            if os.path.exists(filepath):
                # return existing file and skip download
                # return path.join(self.trackstore_dir, filename)
                return filepath

        # filename, filepath, trkid, ytid
        # username = 'default'
        
        # select handler depending on url type    
        if self.from_webapp(url):
            handle = 'webapp/'
            filehandle = ''
            filename = path.basename(components.path)
            location = path.join(self.trackstore_dir + handle, filename)
            
            # if url.startswith('{'):
            #     url_dict = json.loads(url)
            #     url = url_dict['url']
            #     username = url_dict['username']
            # else:
            #     username = 'default'
            
            # command = ['curl', '-s', url, '--output', location]
            # curl with follow redirects enabled
            command = ['curl', '-s', '--location', url, '--output', location]
            # this might also work in case curl is not available
            # self.download_from_webapp(url, location)
            # return location
            
        elif 'soundcloud.com' in components.netloc:
            handle = 'soundscrape/'
            filehandle = path.basename(components.path)
            filename = path.basename(components.path)
            command = ['soundscrape', '-p', self.trackstore_dir + handle + filehandle, url]
        elif 'bandcamp.com' in components.netloc:
            handle = 'soundscrape/'
            filehandle = path.basename(components.path)
            filename = path.basename(components.path)
            command = ['soundscrape', '-b', '-p', self.trackstore_dir + handle + filehandle, url]
        elif 'youtube.com' in components.netloc or 'youtu.be' in components.netloc:
            handle = 'youtube-dl/'
            # command = ['youtube-dl', '-x', '-o', '{0}/%(title)s.%(ext)s'.format(self.trackstore_dir), '--audio-format', 'aac', url]
            # command = ['youtube-dl', '-x', '--audio-format', 'aac', '--get-filename', '-o', '{0}/%(title)s-%(id)s.%(ext)s'.format(self.trackstore_dir), url]
            command = ['youtube-dl', '-x', '--audio-format', ytaudiofmt, '--audio-quality', '4', '-k', '-o', '{0}/%(title)s-%(id)s.%(ext)s'.format(self.trackstore_dir + 'youtube-dl/'), url]
            ytid = components.query.split('v=')[-1]
            # print('    ytid =', ytid)
            filehandle = ''
            filename = ytid
        else:
            raise PlayerError('    Error: unknown url type {0}'.format(components.netloc))

        # run the download command
        try:
            print('    running command {0}'.format(command))
            run(command, check=True)
        except CalledProcessError:
            print('    Error: failed to download from {}'.format(url))
        else:
            # file has been downloaded
            # get the filename
            
            search_dir = self.trackstore_dir + handle + filehandle
            files = list(filter(os.path.isfile, glob.glob(search_dir + "/*")))
            print('    files raw ', search_dir, files)

            # anything not youtube
            if ytid is None:
                # sort by modification time
                files.sort(key=lambda x: os.path.getmtime(x))
                print('        filename', filename)
                print('    files sorted', files)
                # filename is most recent file in listing
                filename = path.basename(files[-1])
            # youtube-dl
            else:
                # filename is the entry matching the youtube id
                # filename = files[files.index(ytid)]
                files = list(filter(os.path.isfile, glob.glob(search_dir + "/*." + ytaudiofmt)))
                filename = list([_ for _ in files if ytid in _])
                print('    ytid filename matches', filename)
                filename = filename[0]
                print('    ytid filename', filename)
                filename = filename.split('/')[-1]
                print('    ytid filename', filename)

            # filepath
            filepath = self.trackstore_dir + handle + filehandle + '/' + filename
            # file length
            filelength = get_filelength(filepath)
            # hash
            filehash = get_filehash(filepath)
            # fingerprint
            # filefp = get_filefp(filepath)
            filefp = 'fingerprint'
            
            # print('filename', filename)

            # not in store
            if trkid == -1:
                
                # # not in store but store has entries
                # if len(self.ts) > 0:
                #     # trkid = self.ts.index.max() + 1
                #     trkid = int(self.ts['id'].max() + 1)
                # # store is empty
                # else:
                #     trkid = 1

                trkid = data_get_index_next(self.ts, indexcol='id')
                    
                # compose new row
                row = [trkid, url, filename, filepath, filelength, filefp, filehash]
                rowdict = dict(zip(data_conf['trackstore_columns'], row))
                print(f'    insert row {row}')
                # self.ts.loc[trkid] = row
                self.ts = data_append_row(rowdict, self.ts)
            # in store but new download on file not found
            else:
                self.ts[self.ts['id'] == trkid]['filename'] = filename
                self.ts[self.ts['id'] == trkid]['filepath'] = filepath
                self.ts[self.ts['id'] == trkid]['filelength'] = filelength
                self.ts[self.ts['id'] == trkid]['filefp'] = filefp
                self.ts[self.ts['id'] == trkid]['filehash'] = filehash

            # self.ts.to_hdf(self.trackstore_filename, self.trackstore_key)
            # self.ts.to_csv(self.trackstore_filename, index=False)
            data_write(self.ts, self.trackstore_filename)

            # row_user = self.ts[self.ts['id'] == trkid] # .to_dict()
            row_user = self.ts[self.ts['id'] == trkid] # .to_dict()
            # del row_user['id']
            print(f'    download {trkid} row_user {row_user}')
            trackstore_user_filename = f'{self.trackstore_filename_base}_{username}.csv'
            ts_user = data_init(
                columns=data_conf['trackstore_columns'],
                filename=trackstore_user_filename)
            
            # try:
            #     ts_user = pd.read_csv(trackstore_user_filename, header=0, sep=',')
            #     # self.trackstore = pd.HDFStore(self.trackstore_filename, mode='a')
            #     # self.ts = pd.read_hdf(self.trackstore_filename, self.trackstore_key)
            # except Exception as e:
            #     print(f'Could not load trackstore_user for user {username} from file at {trackstore_user_filename}')
            #     # continue without trackstore
            #     # self.trackstore = None
            #     # self.trackstore = pd.DataFrame(columns=['id', 'url', 'filename', 'filepath', 'length', 'fingerprint', 'hash'])
            #     ts_user = pd.DataFrame({'id': 0, 'url': 'none', 'filename': 'dummy', 'filepath': 'dummy', 'length': 0, 'fingerprint': '', 'hash': ''}, index=pd.Index([0]))
            #     ts_user.to_csv(trackstore_user_filename, index=False)

            # ts_user = pd.DataFrame(ts_user)
                
            # trkid_user = int(ts_user['id'].max() + 1)
            trkid_user = data_get_index_next(ts_user, indexcol='id')
            row_user['id'] = trkid_user
            
            print(f'    download trkid_user {trkid_user} row_user {row_user}')
            print(f'    download type(ts_user) {type(ts_user)}')
            print(f'    download ts_user df {ts_user.columns}, {ts_user.shape}')

            # ts_user = ts_user.append(row_user, ignore_index=True)
            # ts_user.loc[trkid_user] = row_user.to_list()
            ts_user = data_append_row(row_user, ts_user)

            print(f'    download {ts_user.columns}, {ts_user.shape}')

            # ts_user.to_csv(trackstore_user_filename, index=False)
            data_write(ts_user, trackstore_user_filename)
                
            return filepath # path.join(self.trackstore_dir + handle, filename)

    def from_webapp(self, url):
        for w in self.webapps:
            print(f'    from_webapp "{url}"')
            if url.startswith('{'):
                url_dict = json.loads(url)
                url = url_dict['url']
                username = url_dict['username']
            else:
                username = 'default'
                
            print('player.store from_webapp url {0}, w {1}'.format(url, w))
            if url.startswith(w):
                return True
        return False

    def download_from_webapp(self, url, location):
        """download from webapp

        means "download" file that was uploaded into webapp
        """
        # default track id
        trkid = -1
        # try to get trackinfo from store
        trackinfo = self.ts[self.ts.url == url]

        # track is in the store
        if len(trackinfo) > 0:
            # track is in the store and file does not exist
            trkid = int(trackinfo['id'].astype(object))
            filepath = str(trackinfo.filepath.tolist()[0])
            # print('    found filename {0}'.format(filename))
            # print('    found filepath {0}'.format(filepath))
            
            # track is in the store and file exists            
            if os.path.exists(filepath):
                return filepath

        with requests.get(url, stream=True) as r:
            with open(location, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

    def queue_track(self, track_location):
        if track_location is None:
            return
        for subcommand in ['--append', '--enqueue']:
            command = ['mocp', subcommand, '{0}'.format(track_location)]
            try:
                print('player.store.queue_track\n    command {0}'.format(command))
                run(command, check=True)
            except CalledProcessError as e:
                print(e)
