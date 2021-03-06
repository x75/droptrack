from typing import Dict, Optional, Union
import os
from werkzeug.utils import secure_filename
from multiprocessing import Process
from werkzeug.exceptions import Forbidden, NotFound
from flask import (
    g,
    current_app,
    json,
    request,
    url_for,
    send_from_directory,
    Blueprint,
    Response,
)
from .models import db
from .lib.helpers import (
    validate_url,
    validate_soundfile,
)
from .models import User, Task, Status
from .downloader import download
"""
The main mechanics of the webapp.
"""


api = Blueprint('api', __name__)


@api.before_request
def authenticate() -> Optional[Response]:
    """
    verify token, bind user to request global
    """
    token = request.headers.get('X-Authentication')
    # current_app.logger.info(f'api.authenticate token = {token}')
    if token:
        g.user = User.find_by_api_key(token)
        if g.user:
            return None
        raise Forbidden('Invalid APi key')
    else:
        raise Forbidden('Missing API key')


@api.errorhandler(404)
def not_found(error: NotFound) -> Response:
    message = error.description
    return api_response_error({'message': message}, status=404)


@api.errorhandler(403)
def not_authorized(error: Forbidden) -> Response:
    message = error.description
    return api_response_error({'message': message}, status=403)


def api_response_ok(data: Union[dict, list], status: int = 200) -> Response:
    rv = {'status': 'ok', 'data': data}
    return Response(
        json.dumps(rv),
        content_type='application/json',
        status=status
    )


def api_response_accepted(data: Union[dict, list], location: str) -> Response:
    """
    Send a 202 Accepted Response with a link to the status resource
    in the Location header
    """
    rv = {'status': 'accepted', 'data': data}
    response = Response(
        json.dumps(rv),
        content_type='application/json',
        status=202
    )
    response.headers['Location'] = location
    return response


def api_response_error(
    data: Dict[str, Union[str, dict, list]] = None,
    status: int = 400
) -> Response:
    rv = {'status': 'error', 'data': data}
    return Response(
        json.dumps(rv),
        content_type='application/json',
        status=status
    )


@api.route('/url', methods=['POST'])
def url() -> Response:
    """
    Accept soundfile url, download in the background
    """
    url = request.json.get('url')
    if validate_url(url):
        task = Task(
            name='url download',
            user=g.user,
        )
        db.session.add(task)
        db.session.commit()

        thread = Process(
            target=download,
            args=(url, task.id, g.user.home_directory)
        )
        thread.start()

        return api_response_accepted(
            {'message': 'Url accepted', 'task': task.to_dict()},
            location=task.url
        )
    else:
        return api_response_error({'message': 'Invalid url'}, 400)


@api.route('/files', methods=['GET'])
def list_files() -> Response:
    """
    List files in workspace
    """
    try:
        files = os.listdir(g.user.home_directory)
    except FileNotFoundError:
        raise NotFound('User home directory does not exist')
    else:
        return api_response_ok({
            'files': [
                {'name': name} for name in files if not name.startswith('.')
            ]
        })


@api.route('/files', methods=['POST'])
def upload_file() -> Response:
    """
    Accept direct soundfile upload per multipart/form-data
    """
    file = request.files.get('file')
    if file and validate_soundfile(file):
        filename = secure_filename(file.filename)

        # make sure home directory exists.
        if not os.path.exists(g.user.home_directory):
            g.user.make_home_directory()
            current_app.logger.info(
                f'User Home directory created {g.user.home_directory}'
            )

        location = os.path.join(
            g.user.home_directory,
            filename
        )
        file.save(location)
        url = url_for('api.download_file', filename=filename, _external=True)
        return api_response_ok({'message': 'File accepted'})
    else:
        return api_response_error({'message': 'Invalid File'})


@api.route('/files/<path:filename>', methods=['GET'])
def download_file(filename: str) -> Response:
    """
    Retrieve stored file
    """
    current_app.logger.info(f"download {filename}")
    return send_from_directory(
        g.user.home_directory,
        filename,
        as_attachment=True
    )
    

@api.route('/files/<path:filename>', methods=['DELETE'])
def delete_file(filename: str) -> Response:
    """
    Delete stored file
    """
    location = os.path.join(
        g.user.home_directory,
        filename
    )
    try:
        os.unlink(location)
    except FileNotFoundError:
        raise NotFound('File not found')
    else:
        return api_response_ok({'message': f'file "{filename}" deleted'})


@api.route('/tasks')
def list_tasks() -> Response:
    """
    Task List
    """
    return api_response_ok({
        'data': [
            t.to_dict() for t in g.user.tasks
        ]
    })


@api.route('/tasks/<uuid:uuid>', methods=['PUT'])
def update_task(uuid) -> Response:
    """
    Update Task status and result_location
    """
    task = Task.query.filter(
        Task.uuid == uuid,
        Task.user_id == g.user.id
    ).first()

    if not task:
        raise NotFound('Task not found')

    try:
        task.status = Status[request.json['status']]
        task.result_location = request.json['result_location']
    except Exception as e:
        return api_response_error({'message': str(e)})
    else:
        db.session.add(task)
        db.session.commit()
    return api_response_ok(task.to_dict())


@api.route('/tasks/<uuid:uuid>', methods=['GET'])
def show_task(uuid) -> Response:
    """
    Task details and status 202 if still processing
    """
    task = Task.query.filter(
        Task.uuid == uuid,
        Task.user_id == g.user.id
    ).first()

    if not task:
        raise NotFound('Task not found')

    if task.is_processing:
        return api_response_accepted(task.to_dict(), location=task.url)
    else:
        return api_response_ok(task.to_dict())


@api.route('/actions')
def list_actions() -> Response:
    """
    Action Catalog
    :param str:
    """
    return api_response_ok([
        {
            'name': 'autoedit',
            'url': '/api/autoedit',
            'parameters': {
                'files': [],
                'assemble_mode': 'random',
                'assemble_crossfade': 10,
                'duration': 180,
                'numsegs': 23,

# TODO device a way to pass parameter mapping from python to javascript
#
#                'files': {'type': List[File], 'range': Any, 'default': None},
#                'assemble_mode': {
#                   'type': str,
#                   'range': random|sequential,
#                   'default': 'random'
#                },
#                'assemble_crossfade': {
#                    'type': number,
#                    'range': 0-99999,
#                    'default': 10
#                },
#                'duration': {
#                    'type': number,
#                    'range': 0-99999,
#                    'default': 180
#                },
            }
        },
        {
            'name': 'autocover',
            'url': '/api/autocover',
            'parameters': {
                'output_format': ['jpg']
            }
        },
        {
            'name': 'automaster',
            'url': '/api/automaster',
            'parameters': {
                'bitdepth': 16
            }
        }
    ])


#@api.route('/actions/<any(autoedit,autocover):action>', methods=['POST'])
#def show_action(action: str):
#    data = request.json
#    files = data['files']
#    name = files[0]['name']
#    task = Task(
#        name=f'{action} {name}',
#        user=g.user,
#    )
#    db.session.add(task)
#    db.session.commit()
#    return api_response_ok(task.to_dict())
