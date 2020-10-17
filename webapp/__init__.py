# -*- coding: utf-8 -*-
import random, string, time, json
import atexit
from logging import Formatter
from logging.handlers import SysLogHandler
import os
from os import listdir
from os.path import isfile, join
from os import walk
from pprint import pformat

from werkzeug.utils import secure_filename
from flask import (
    Flask,
    current_app,
    flash,
    g,
    jsonify,
    make_response,
    Response,
    request,
    render_template,
    redirect,
    send_from_directory,
    session,
    url_for,
)
from .lib import (
    validate_url,
    validate_soundfile,
    download
)
from webapp.queue import Queue

import pandas as pd
from webapp.libdata import data_conf
from webapp.libdata import data_init, data_get_columns, data_append_row, data_write, data_get_index_next

try:
    APP_ENV = os.environ['APP_ENV']
except KeyError:
    APP_ENV = 'config.Config'

# BASE_PATH='/droptrack'
BASE_PATH=''
    
def generate_username(length=4):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    print("    generate_username: random string of length", length, "is:", result_str)
    return result_str

def store_user_session(username):
    # user_session_log_file = 'data/user_session_log.csv'
    # user_session_log_file = data_conf['user_session_log_file']
    # user_session_log = pd.read_csv(user_session_log_file, sep=',', header=0)
    
    user_session_log = data_init(columns=data_conf['user_session_columns'], filename=data_conf['user_session_log_file'])
    if len(user_session_log.index) < 1:
        user_session_log_max_idx = -1
    else:
        user_session_log_max_idx = user_session_log.index[-1]
    print(f'    store_user_session user_session_log {user_session_log}\n    user_session_log_max_idx {user_session_log_max_idx}')
    
    datetime = time.strftime('%Y-%m-%d %H:%M:%S')
    IP = request.remote_addr
    row = {'username': username, 'datetime': datetime, 'IP': IP}
    userid = user_session_log_max_idx + 1
    print(f'    store_user_session insert row {row}\n    at loc[{userid}]')
    
    # user_session_log = user_session_log.loc[userid] = row
    # user_session_log = user_session_log.append(row, ignore_index=True)
    # user_session_log.to_csv(user_session_log_file)
    
    data_append_row(row, user_session_log)
    data_write(user_session_log, data_conf['user_session_log_file'])
    return

def session_init():
    """check session cookie
    
    check if 'username' is in session cookie
    """
    d = {}
    if 'username' not in request.cookies:
        username = generate_username(4)
        print(f'    webapp session_init creating username {username}')

        store_user_session(username)
    else:
        username = request.cookies["username"]
        print(f'    webapp session_init getting username {username}')
    
    for k in request.cookies:
        d[k] = request.cookies[k]
    return d

def session_close(resp_html, session_dict):
    # create response
    resp = make_response(
        resp_html
    )

    resp = set_cookies(resp, session_dict)
    return resp
    
def set_cookies(resp, cookies):
    # set cookie on response for each key
    for k in cookies:
        if k not in request.cookies:        
            print(f'    updating cookie[{k}] to {cookies[k]}')
            resp.set_cookie(k, cookies[k])
        if k in request.cookies:
            if cookies[k] != request.cookies[k]:
                print(f'    updating cookie[{k}] to {cookies[k]}')
                resp.set_cookie(k, cookies[k])
    return resp

def root():
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']
    
    # default tracklist
    tracklist_filename = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username)
    tracklist = data_init(data_conf['trackstore_columns'], tracklist_filename)
    print(f'tracklist {tracklist.columns} {tracklist.shape}')

    # base_path = BASE_PATH # request.path
    print(f'    webapp root base_path {current_app.config["BASE_PATH"]}')

    resp_html = render_template(
        'url.html', username=username, tracklist=tracklist,
        base_path=current_app.config["BASE_PATH"]
    )

    return session_close(resp_html, session_dict)

def url():
    """
    Accept soundfile url
    """
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']
    
    # assert 'username' in request.cookies, 'Require username, please restart app from root level'
    if request.method == 'POST':
        url = request.form.get('url')
        if validate_url(url):
            if 'username' in request.cookies:
                username = request.cookies["username"]
                # jsonstr = jsonify({'url': url, 'username': username})
                jsonstr = json.dumps({'url': url, 'username': username})
                print(f'    url {url}\njsonstr {jsonstr}')
                current_app.queue.send(jsonstr)
                erfolg = f'JUHUUU Erfolg! {username}'
            else:
                current_app.queue.send(url)
                erfolg = 'JUHUUU Erfolg!'
            flash(erfolg)
        else:
            flash('Sorry, this did not work. Please try again')
    return redirect(f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/')

def tracklist():
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']
    
    # assert 'username' in request.cookies, 'Require username, please restart app from root level'
    
    # tracklist_filename = f'{conf["trackstore_filename_base"]}_{username}.csv'
    # tracklist = pd.read_csv(tracklist_filename)
    tracklist_filename = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username)
    tracklist = data_init(data_conf['trackstore_columns'], tracklist_filename)
    print(f'    loaded tracklist\n        from {tracklist_filename}\n    into {tracklist.columns} {tracklist.shape}')

    # tracklist_filename_default = f'{conf["trackstore_filename_base"]}_default.csv'
    # tracklist_default = pd.read_csv(tracklist_filename_default)
    tracklist_filename_default = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], 'default')
    tracklist_default = data_init(data_conf['trackstore_columns'], tracklist_filename_default)

    resp_html = render_template(
        'tracklist.html', tracklist=tracklist,
        tracklist_default=tracklist_default, username=username,
        base_path=current_app.config["BASE_PATH"]
    )

    return session_close(resp_html, session_dict)

def run_autoedit(args):
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    # assert 'username' in request.cookies, 'Require username, please restart app from root level'
    
    print(f'autoedit args {type(args)}')
    # print(f'autoedit request {dir(request)}')
    # print(f'autoedit request {request.json}')
    # print(f'autoedit request {request.form}')

    # import main_autoedit
    from smp_audio.autoedit import main_autoedit
    # create argparse.Namespace from request.form
    from argparse import Namespace
    args = Namespace()
    # run main_autoedit with args
    
    for k in request.form:
        setattr(args, k, request.form[k])

    args.numsegs = int(args.numsegs)
    args.seed = int(args.seed)
    args.duration = int(args.duration)

    # tracklist = pd.read_csv('{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username))
    tracklist_filename = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username)
    tracklist = data_init(data_conf['trackstore_columns'], tracklist_filename)
    
    trackid = int(request.form.get('trackid'))
    # track = tracklist.loc[trackid]
    track = tracklist[tracklist['id'] == trackid].squeeze()

    # filename = track.filename
        
    args.filenames = [track.filepath]
    args.mode = 'autoedit'
    args.sr_comp=22050
    args.sorter='features_mt_spectral_spread_mean'
    args.seglen_min=2
    args.seglen_max=60
    args.write=False

    args.assemble_mode = request.form.get('assemble_mode')
    args.assemble_crossfade = 10
    
    print(f'run_autoedit args {args}')

    autoedit_res = main_autoedit(args)
        
    print(f'run_autoedit res {autoedit_res}')
    
    return autoedit_res

# def trackdl():
#     path = request.form[trackpath]
#     return send_from_directory('data/download', path)

def track():
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    # assert 'username' in request.cookies, 'Require username, please restart app from root level'

    # handle request methods
    if request.method == 'POST':
        # print(f'track, got post {request}')
        trackid = int(request.form.get('trackid'))
        mode = request.form.get('mode')
    else:
        trackid = request.args.get('trackid')
        if trackid is None:
            flash('no trackid')
            return redirect(f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/tracklist')
        trackid = int(trackid)
        mode = "show"
    print(f'    track: session {session.keys()}')
    print(f'    track: cookies {request.cookies.keys()}')
    
    # load tracks
    # tracklist = pd.read_csv('{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username))
    tracklist_filename = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username)
    tracklist = data_init(data_conf['trackstore_columns'], tracklist_filename)
    # get track
    # track = tracklist.loc[trackid].to_dict()
    # track = tracklist[tracklist['id'] == trackid].to_dict()
    track = tracklist[tracklist['id'] == trackid].squeeze().to_dict()
    print(f'track {track}\nmode {mode}')

    autoedit_res = {
        'filename_export': None, 'length': None,
        'segs': None, 'final_duration': 0, 'seg_s': 0
    }

    if mode == "autoedit":
        autoedit_res_ = run_autoedit(track)
        autoedit_res.update(autoedit_res_)

    print(f'    autoedit_res {autoedit_res}')
    
    # record results
    # results_filename = '{0}_{1}_{2}.csv'.format(data_conf['trackstore_filename_base'], username, trackid)
    autoedit_results_filename = '{0}_{1}_{2}.csv'.format(data_conf['trackstore_filename_base'], username, trackid)
    autoedit_results = data_init(data_conf['autoedit_response_columns'], autoedit_results_filename)
    
    print(f'    autoedit_results_filename {autoedit_results_filename}')
    print(f'    autoedit_results {autoedit_results}')

    # try:
    #     ts_autoedit = pd.read_csv(autoedit_results_filename)
    #     print(f'    ts_autoedit pre append {ts_autoedit}')
    #     # self.trackstore = pd.HDFStore(self.trackstore_filename, mode='a')
    #     # self.ts = pd.read_hdf(self.trackstore_filename, self.trackstore_key)
    # except Exception as e:
    #     print('Could not load trackstore from file at {0}'.format(results_filename))
    #     # continue without trackstore
    #     # self.trackstore = None
    #     # self.trackstore = pd.DataFrame(columns=['id', 'url', 'filename', 'filepath', 'length', 'fingerprint', 'hash'])
    #     # autoedit_res['id'] = 0
    #     autoedit_res_keys = data_conf['autoedit_response_columns']
    #     ts_autoedit = pd.DataFrame(columns=autoedit_res_keys, index=pd.Index([0]))
    #     autoedit_res['id'] = 0
    #     print(f'    ts_autoedit new table {ts_autoedit}')

    if mode == "autoedit":
        # if len(ts_autoedit.index) < 1:
        #     ts_autoedit_max_idx = -1
        # else:
        #     ts_autoedit_max_idx = ts_autoedit.index[-1]
        # autoedit_res['id'] = ts_autoedit_max_idx + 1
        # ts_autoedit = ts_autoedit.append(autoedit_res, ignore_index=True)
        autoedit_res['id'] = data_get_index_next(autoedit_results, indexcol='id')
        autoedit_results = data_append_row(autoedit_res, autoedit_results)
        print(f'    autoedit_results post append {autoedit_results}')

        data_write(autoedit_results, autoedit_results_filename)

    media_server = current_app.config['MEDIA_SERVER']
    print(f'    tracklist media_server {media_server}')
    
    # print(f'    track: autoedit_res {autoedit_res}')
    resp_html = render_template(
        'track.html', name="opt", tracklist=track, username=username,
        autoedit_res=autoedit_res, autoedit_results=autoedit_results,
        media_server=media_server,
        base_path=current_app.config["BASE_PATH"]
    )

    return session_close(resp_html, session_dict)

def upload():
    """
    Accept soundfile upload
    """
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    # assert 'username' in request.cookies, 'Require username, please restart app from root level'

    if request.method == 'POST':
        soundfile = request.files.get('soundfile')
        print(f'    upload from soundfile {soundfile}')
        if validate_soundfile(soundfile):
            filename = secure_filename(soundfile.filename)
            location = os.path.join(
                current_app.config['UPLOAD_DIR'],
                filename
            )
            soundfile.save(location)
            url = url_for('download', filename=filename, _external=True)
            print(f'    upload saved file url_for {url}')
            url = f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/soundfile/{filename}'
            print(f'    upload saved file url_sf {url}')
            url = f'{request.host_url[:-1]}{current_app.config["BASE_PATH"]}/data/upload/{filename}'
            print(f'    upload saved file url {url}')
            if 'username' in request.cookies:
                username = request.cookies["username"]
                # jsonstr = jsonify({'url': url, 'username': username})
                jsonstr = json.dumps({'url': url, 'username': username})
                print(f'    upload jsonstr {jsonstr}')
                current_app.queue.send(jsonstr)
                erfolg = f'JUHUUU Erfolg! {username}'
            else:
                erfolg = 'JUHUUU Erfolg!'
                jsonstr = url
            current_app.queue.send(jsonstr)
            flash(erfolg)
        else:
            flash('Sorry. Upload Failed.')

    return redirect(f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/')


def download(filename):
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    return send_from_directory(
        current_app.config['UPLOAD_DIR'],
        filename,
        as_attachment=True
    )

def assets(filename):
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    return send_from_directory(
        current_app.config['ASSETS_DIR'],
        filename,
        as_attachment=False
    )

def setsession():
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    # # check if username in session cookie
    # if 'username' not in request.cookies:
    #     username = generate_username(4)
    #     print(f'creating username {username}')

    #     store_user_session(username)
    # else:
    #     username = request.cookies["username"]
    #     print(f'getting cookie {username}')
    
    if request.method == 'POST':
        sessionkey = request.form.get('sessionkey')
        
        # set cookie on response
        # if 'username' not in request.cookies:        
        print(f'setting cookie[username] to {sessionkey}')
        resp.set_cookie('username', sessionkey)
        session_dict['username'] = sessionkey
            
        erfolg = f'JUHUUU Erfolg! changed session from {username} to {sessionkey}'
        flash(erfolg)
        
        # return redirect(f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/setsession')

    # create response
    resp_html = render_template(
        'session.html', username=username,
        base_path=current_app.config["BASE_PATH"]
    )

    # return resp

    return session_close(resp_html, session_dict)

def autodeck_get_count():
    """autodeck get count

    load autodeck count from file, if it does not exist, init zero and
    save to file.
    """
    autodeck_count_filename = 'data/autoedit/autodeck-count.txt'
    if os.path.exists(autodeck_count_filename):
        autodeck_count = int(open(autodeck_count_filename, 'r').read().strip())
        print(f'autodeck_get_count from file {autodeck_count}, {type(autodeck_count)}')
    else:
        autodeck_count = 0
        print(f'autodeck_get_count file no found, init {autodeck_count}')
    autodeck_count_new = autodeck_count + 1
    f = open(autodeck_count_filename, 'w')
    f.write(f'{autodeck_count_new}\n')
    f.flush()
    return autodeck_count

def make_item_choice(filemap, item, deck):

    filemap_filt = [_ for _ in filemap[item] if _['deck'] == deck ]
    if len(filemap_filt) < 1:
        item_choice = random.choice(filemap[item])
    else:
        item_choice = random.choice(filemap_filt)

    return item_choice

def run_autodeck(**kwargs):
    
    # print(f'        run_autodeck kwargs {kwargs}')
    if 'sequence' not in kwargs:
        return {
            'autodeck': False,
        }

    if 'filemap' not in kwargs:
        return {
            'autodeck': False,
        }

    if 'deck' not in kwargs:
        return {
            'autodeck': False,
        }

    sequence = kwargs['sequence'].split(' ')
    deck = kwargs['deck']
    print(f'    run_autodeck deck {deck}')
    # filemap is dict with keys for categories pointing to lists of files
    filemap = kwargs['filemap']
    item_choices = []
    for i, item in enumerate(sequence):
        # print(f'    run_ad item_{i} {item}')
        # print(f'    run_ad item_{i} {filemap[item]}')
        item_choice = make_item_choice(filemap, item, deck)
        print(f'        run_autodeck item_choice {item} {item_choice}')
        item_choices.append(item_choice)
    
    return {
        'autodeck': True,
        'sequence': sequence,
        'item_choices': item_choices,
    }

def autodeck():
    # check session cookie
    session_dict = session_init()
    username = session_dict['username']

    # assert 'username' in request.cookies, 'Require username, please restart app from root level'

    # handle request methods
    if request.method == 'POST':
        print(f'    autodeck POST {request} {request.form}')
        # trackid = int(request.form.get('trackid'))
        for k in request.form:
            print(f'    autodeck form key {k}')
            session_dict[k] = request.form[k]
        # mode = request.form.get('mode')
        mode = session_dict['mode']
    else:
        print(f'autodeck GET {request}')
        # trackid = request.args.get('trackid')
        # if trackid is None:
        #     flash('no trackid')
        #     return redirect(f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/tracklist')
        # trackid = int(trackid)
        mode = "show"
    print(f'    autodeck: session {session.keys()}')
    print(f'    autodeck: cookies {request.cookies.keys()}')

    # assemble page content

    # prior categories
    categories = set([
        'contact', 'vision', 'tech', 'people', 'product', 'market',
        'deck', 'story',
    ])
    # print(f'    autodeck: prior categories {categories}')
    
    # get slides
    mypath = '/home/src/QK/droptrack/data/autodeck'
    mypath_categories = mypath + '/categories'
    mypath_generated = mypath + '/generated'

    # get list of generated decks
    generated_decks = [f for f in listdir(mypath_generated) if isfile(join(mypath_generated, f)) and 'autodeck' in f]
    
    # get all directories
    onlydirs = []
    for (dirpath, dirnames, filenames) in walk(mypath_categories):
        # f.extend(filenames)
        onlydirs.extend(dirnames)
        break
    # print(f'    autodeck: onlydirs {onlydirs}')

    # update prior categories
    for dirname in onlydirs:
        categories.add(dirname)
    # print(f'    autodeck: posterior categories {categories}')
    
    onlyfiles = []
    for onlydir in onlydirs:
        onlydir2 = mypath_categories + '/' + onlydir
        # print(f'    onlydir2 {onlydir2}')
        l_ = [f for f in listdir(onlydir2) if isfile(join(onlydir2, f))]
        onlyfiles.extend(l_)
    # print(f'    onlyfiles {onlyfiles}')

    # TODO sort this list into dict
    filemap = dict(zip(categories, [[] for c_ in categories]))
    # print(f'    autodeck: filemap {pformat(filemap)}')
    
    deck_skins = set()
    for onlyfile in onlyfiles:
        # print(f'    onlyfile {onlyfile}')
        # onlyfile_l = onlyfile.split('-')
        onlyfile_l = onlyfile.split('_')
        # print(f'    onlyfile_l {onlyfile_l}')

        # numbers, numbers, deck-1, rest

        # add deck to set of skins
        deck_skins.add(onlyfile_l[1])

        # add filename, deck skin, subcat to filemap dict
        filemap[onlyfile_l[0]].append(
            {
                'filename': onlyfile,
                'deck': onlyfile_l[1],
                'subcat': onlyfile_l[2]
            }
        )
    print(f'    autodeck: filemap {pformat(filemap)}')
    
    autodeck_result = None
    # {
    #     # 'filename_export': None,
    #     # 'length': None,
    #     # 'segs': None,
    #     # 'final_duration': 0,
    #     # 'seg_s': 0
    #     'filemap': filemap
    # }

    if mode == "autodeck":
        # print(f'    autodeck am start')
        autodeck_result = run_autodeck(
            sequence=session_dict['sequence'],
            filemap=filemap,
            deck=session_dict['deck_skin'],
        )
        # data_write(autoedit_results, autoedit_results_filename)
    if autodeck_result is not None:
        # {random.randint(0, 1000000)
        autodeck_count = autodeck_get_count()
        # print(f'    autodeck autodeck_result {pformat(autodeck_result)}')
        from pdfrw import PdfReader, PdfWriter, IndirectPdfDict
        outfilename = f'/home/src/QK/droptrack/data/autodeck/generated/autodeck-{autodeck_count}-{len(autodeck_result["item_choices"])}-{session_dict["deck_skin"]}.pdf' 
        writer = PdfWriter()
        for i, slide in enumerate(autodeck_result['item_choices']):
            slidecat = autodeck_result['sequence'][i]
            slidefilename = '/home/src/QK/droptrack/data/autodeck/categories' + '/' + \
                            slidecat + '/' + \
                            slide['filename']
            print(f'        autodeck i {i} slidefilename {slidefilename} {slidecat}')
            
            writer.addpages(PdfReader(slidefilename).pages)

        writer.trailer.Info = IndirectPdfDict(
            Title='your title goes here',
            Author='your name goes here',
            Subject='what is it all about?',
            Creator='some script goes here',
        )
        writer.write(outfilename)       

    media_server = current_app.config['MEDIA_SERVER']
    # print(f'    autodeck media_server {media_server}')

    deckid = random.randint(0, 100)
    
    resp_html = render_template(
        'autodeck.html', name="opt", username=username,
        media_server=media_server, base_path=current_app.config["BASE_PATH"],
        deckid = deckid, categories=categories,
        generated_decks=generated_decks, onlyfiles=onlyfiles,
        filemap=filemap, deck_skins=deck_skins,
        session_dict=session_dict
    )

    return session_close(resp_html, session_dict)

def data_serve_static():
    print(f'dir request {dir(request)}')

def setup_routes(app):
    url.methods = ['GET', 'POST']
    upload.methods = ['POST']
    track.methods = ['GET', 'POST']
    setsession.methods = ['GET', 'POST']
    autodeck.methods = ['GET', 'POST']
    
    app.add_url_rule('/', 'root', root)
    app.add_url_rule('/url', 'url', url)
    # app.add_url_rule('/data', 'data', data_serve_static)
    app.add_url_rule('/soundfile', 'upload', upload)
    app.add_url_rule('/soundfile/<path:filename>', 'download', download)
    app.add_url_rule('/track', 'track', track)
    # app.add_url_rule('/trackdl', 'trackdl', trackdl)
    app.add_url_rule('/tracklist', 'tracklist', tracklist)
    app.add_url_rule('/setsession', 'setsession', setsession)
    app.add_url_rule('/assets/<path:filename>', 'assets', assets)
    # pitck deck generator
    app.add_url_rule('/autodeck', 'autodeck', autodeck)

    
def setup_queue(app):
    app.queue = Queue(app.config)
    atexit.register(app.queue.shutdown)


def setup_logging(app):
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    default_level = 'debug' if app.config['DEBUG'] else 'info'
    address = app.config.get('LOG_ADDRESS', '/dev/log')
    facility = app.config.get('LOG_FACILITY', 'LOG_SYSLOG')
    level = app.config.get('LOG_LEVEL', default_level)
    handler = SysLogHandler(
        address=address,
        facility=SysLogHandler.__dict__[facility],
    )
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)


def create_app():
    """
    Using the app-factory pattern
    :return Flask:
    """
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates'
    )
    app.config.from_object(APP_ENV)
    setup_routes(app)
    setup_queue(app)
    setup_logging(app)
    return app
