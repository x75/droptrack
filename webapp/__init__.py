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

try:
    APP_ENV = os.environ['APP_ENV']
except KeyError:
    APP_ENV = 'config.Config'

def generate_username(length=4):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    print("    generate_username: random string of length", length, "is:", result_str)
    return result_str

def store_user_session(username):
    user_session_log_file = 'data/user_session_log.csv'
    user_session_log = pd.read_csv(user_session_log_file, sep=',', header=0)
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
    user_session_log = user_session_log.append(row, ignore_index=True)
    user_session_log.to_csv(user_session_log_file)
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
    tracklist = pd.read_csv('data/player_trackstore.csv')
    print(f'tracklist {tracklist.columns} {tracklist.shape}')

    # create response
    resp = make_response(render_template('url.html', username=username, tracklist=tracklist))

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
    return redirect('/')

def tracklist():
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    if 'username' in request.cookies:
        username = request.cookies["username"]
    else:
        username = 'default'

    tracklist_filename = f'data/player_trackstore_{username}.csv'
    tracklist = pd.read_csv(tracklist_filename)
    print(f'    loaded tracklist\n        from {tracklist_filename}\n    into {tracklist.columns} {tracklist.shape}')
    return render_template('tracklist.html', tracklist=tracklist, username=username)

def run_autoedit(args):
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

    tracklist = pd.read_csv('data/player_trackstore.csv')
    trackid = int(request.form.get('trackid'))
    track = tracklist.loc[trackid]

    # filename = track.filename
        
    args.filenames = [track.filepath]
    args.mode = 'autoedit'
    args.sr_comp=22050
    args.sorter='features_mt_spectral_spread_mean'
    args.seglen_min=2
    args.seglen_max=60
    args.write=False
        
    print(f'run_autoedit args {args}')

    autoedit_res = main_autoedit(args)
        
    print(f'run_autoedit res {autoedit_res}')
    
    return autoedit_res

def trackdl():
    path = request.form[trackpath]
    return send_from_directory('data/download', path)

def track():
    assert 'username' in request.cookies, 'Require username, please restart app from root level'
    if request.method == 'POST':
        # print(f'track, got post {request}')
        trackid = int(request.form.get('trackid'))
        mode = request.form.get('mode')
    else:
        trackid = request.args.get('trackid')
        if trackid is None:
            flash('no trackid')
            return redirect('/tracklist')
        trackid = int(trackid)
        mode = "show"
    print(f'    track: session {session.keys()}')
    print(f'    track: cookies {request.cookies.keys()}')
    
    # if 'user' not in request.cookies:
    #     # request.cookies.put
    #     resp.set_cookie('username', 'the username')
        
    # load tracks
    tracklist = pd.read_csv('data/player_trackstore.csv')
    # get track
    track = tracklist.loc[trackid]
    # print(f'track {track}\nmode {mode}')
    if mode == "autoedit":
        autoedit_res = run_autoedit(track)
    else:
        autoedit_res = {'filename': None, 'length': None, 'segs': None}
    print(f'    track: autoedit_res {autoedit_res}')
    return render_template('track.html', name="opt", tracklist=track, autoedit_res=autoedit_res)

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

    return redirect('/')


def download(filename):
    return send_from_directory(
        current_app.config['UPLOAD_DIR'],
        filename,
        as_attachment=True
    )


def data_serve_static():
    print(f'dir request {dir(request)}')

def setup_routes(app):
    url.methods = ['GET', 'POST']
    upload.methods = ['POST']
    track.methods = ['GET', 'POST']
    
    app.add_url_rule('/', 'root', root)
    app.add_url_rule('/url', 'url', url)
    # app.add_url_rule('/data', 'data', data_serve_static)
    app.add_url_rule('/soundfile', 'upload', upload)
    app.add_url_rule('/soundfile/<path:filename>', 'download', download)
    app.add_url_rule('/track', 'track', track)
    app.add_url_rule('/trackdl', 'trackdl', trackdl)
    app.add_url_rule('/tracklist', 'tracklist', tracklist)

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
