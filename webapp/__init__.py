# -*- coding: utf-8 -*-
import random, string, time, json
import atexit
from logging import Formatter
from logging.handlers import SysLogHandler
import os
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

def root():
    # check if username in session cookie
    if 'username' not in request.cookies:
        username = generate_username(4)
        print(f'creating username {username}')

        store_user_session(username)
    else:
        username = request.cookies["username"]
        print(f'getting cookie {username}')

    # default tracklist
    # tracklist = pd.read_csv('{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username))
    tracklist_filename = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username)
    tracklist = data_init(data_conf['trackstore_columns'], tracklist_filename)
    print(f'tracklist {tracklist.columns} {tracklist.shape}')

    # base_path = BASE_PATH # request.path
    print(f'    webapp root base_path {current_app.config["BASE_PATH"]}')
    
    # create response
    resp = make_response(
        render_template(
            'url.html', username=username, tracklist=tracklist,
            base_path=current_app.config["BASE_PATH"]
        ))

    # set cookie on response
    if 'username' not in request.cookies:        
        print(f'setting cookie[username] to {username}')
        resp.set_cookie('username', username)
    return resp

def url():
    """
    Accept soundfile url
    """
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    if request.method == 'POST':
        url = request.form.get('url')
        if validate_url(url):
            if 'username' in request.cookies:
                username = request.cookies["username"]
                jsonstr = jsonify({'url': url, 'username': username})
                print(f'    url jsonstr {jsonstr}')
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
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    if 'username' in request.cookies:
        username = request.cookies["username"]
    else:
        username = 'default'

    # tracklist_filename = f'{conf["trackstore_filename_base"]}_{username}.csv'
    # tracklist = pd.read_csv(tracklist_filename)
    tracklist_filename = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], username)
    tracklist = data_init(data_conf['trackstore_columns'], tracklist_filename)
    print(f'    loaded tracklist\n        from {tracklist_filename}\n    into {tracklist.columns} {tracklist.shape}')

    # tracklist_filename_default = f'{conf["trackstore_filename_base"]}_default.csv'
    # tracklist_default = pd.read_csv(tracklist_filename_default)
    tracklist_filename_default = '{0}_{1}.csv'.format(data_conf['trackstore_filename_base'], 'default')
    tracklist_default = data_init(data_conf['trackstore_columns'], tracklist_filename_default)

    return render_template(
        'tracklist.html', tracklist=tracklist,
        tracklist_default=tracklist_default, username=username,
        base_path=current_app.config["BASE_PATH"]
    )

def run_autoedit(args):
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    # get user_session
    if 'username' in request.cookies:
        username = request.cookies["username"]
    else:
        username = 'default'
        
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

def trackdl():
    path = request.form[trackpath]
    return send_from_directory('data/download', path)

def track():
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    # get user_session
    if 'username' in request.cookies:
        username = request.cookies["username"]
    else:
        username = 'default'

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
    return render_template(
        'track.html', name="opt", tracklist=track, username=username,
        autoedit_res=autoedit_res, autoedit_results=autoedit_results,
        media_server=media_server,
        base_path=current_app.config["BASE_PATH"]
    )

def upload():
    """
    Accept soundfile upload
    """
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
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
    return send_from_directory(
        current_app.config['UPLOAD_DIR'],
        filename,
        as_attachment=True
    )

def assets(filename):
    return send_from_directory(
        current_app.config['ASSETS_DIR'],
        filename,
        as_attachment=False
    )

def setsession():
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    # get user_session
    if 'username' in request.cookies:
        username = request.cookies["username"]
    else:
        username = 'default'
    
    # # check if username in session cookie
    # if 'username' not in request.cookies:
    #     username = generate_username(4)
    #     print(f'creating username {username}')

    #     store_user_session(username)
    # else:
    #     username = request.cookies["username"]
    #     print(f'getting cookie {username}')
    
    # create response
    resp = make_response(
        render_template(
            'session.html', username=username,
            base_path=current_app.config["BASE_PATH"]
        ))

    if request.method == 'POST':
        sessionkey = request.form.get('sessionkey')
        
        # set cookie on response
        # if 'username' not in request.cookies:        
        print(f'setting cookie[username] to {sessionkey}')
        resp.set_cookie('username', sessionkey)
            
        erfolg = f'JUHUUU Erfolg! changed session from {username} to {sessionkey}'
        flash(erfolg)
        
        # return redirect(f'{request.host_url[:-1]}/{current_app.config["BASE_PATH"]}/setsession')
    return resp

def data_serve_static():
    print(f'dir request {dir(request)}')

def setup_routes(app):
    url.methods = ['GET', 'POST']
    upload.methods = ['POST']
    track.methods = ['GET', 'POST']
    setsession.methods = ['GET', 'POST']
    
    app.add_url_rule('/', 'root', root)
    app.add_url_rule('/url', 'url', url)
    # app.add_url_rule('/data', 'data', data_serve_static)
    app.add_url_rule('/soundfile', 'upload', upload)
    app.add_url_rule('/soundfile/<path:filename>', 'download', download)
    app.add_url_rule('/track', 'track', track)
    app.add_url_rule('/trackdl', 'trackdl', trackdl)
    app.add_url_rule('/tracklist', 'tracklist', tracklist)
    app.add_url_rule('/setsession', 'setsession', setsession)
    app.add_url_rule('/assets/<path:filename>', 'assets', assets)

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
