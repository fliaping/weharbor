"""Allowlisted desktop application restarts, executed as the desktop user."""
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

APPS = {
    'wechat': {'executable': '/opt/wechat/wechat', 'prefix': '/opt/wechat/',
               'command': ['/usr/bin/wechat']},
    'weflow': {'executable': '/opt/weflow/weflow', 'prefix': '/opt/weflow/',
               'command': ['/opt/weflow/weflow', '--no-sandbox']},
}


class RestartBusy(Exception):
    pass


def permitted_request(headers, host, content_type):
    # A custom header and JSON require a CORS preflight for cross-origin pages.
    # This service grants no CORS permissions. Also check browser origin metadata.
    if headers.get('X-WeHarbor-Action') != 'restart' or content_type != 'application/json':
        return False
    if headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none'):
        return False
    origin = headers.get('Origin')
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or parsed.netloc.lower() != host.lower():
            return False
    return True


class AppController:
    def __init__(self):
        self.locks = {name: threading.Lock() for name in APPS}
        self.children = {}

    @staticmethod
    def processes(app):
        result = {}
        for directory in Path('/proc').glob('[0-9]*'):
            try:
                if directory.stat().st_uid != os.getuid():
                    continue
                executable = str((directory / 'exe').resolve(strict=True))
                if not executable.startswith(APPS[app]['prefix']):
                    continue
                fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] == 'Z':
                    continue
                arguments = (directory / 'cmdline').read_bytes().split(b'\0')
                main = executable == APPS[app]['executable'] and not any(
                    arg.startswith(b'--type=') for arg in arguments)
                result[int(directory.name)] = (fields[19], main)
            except (OSError, ValueError):
                continue
        return result

    def status(self):
        result = {}
        for name in APPS:
            child = self.children.get(name)
            if child is not None:
                child.poll()  # Reap applications we launched after they exit.
            result[name] = {
                'running': any(main for _, main in self.processes(name).values()),
                'restarting': self.locks[name].locked(),
            }
        return result

    def send(self, app, targets, signum):
        current = self.processes(app)
        for pid, identity in targets.items():
            if current.get(pid) == identity:
                try:
                    os.kill(pid, signum)
                except ProcessLookupError:
                    pass

    def wait_stopped(self, app, targets, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            current = self.processes(app)
            if not any(current.get(pid) == identity for pid, identity in targets.items()):
                return True
            time.sleep(0.1)
        current = self.processes(app)
        return not any(current.get(pid) == identity for pid, identity in targets.items())

    def restart(self, app):
        if app not in APPS:
            raise ValueError('Unknown application')
        if os.getuid() == 0:
            raise RuntimeError('Application controls require the desktop user')
        if not self.locks[app].acquire(blocking=False):
            raise RestartBusy()
        try:
            targets = self.processes(app)
            mains = {pid: value for pid, value in targets.items() if value[1]}
            self.send(app, mains, signal.SIGTERM)
            self.wait_stopped(app, mains, 8)
            # Stop only this user's remaining vendor processes, including helpers.
            targets.update(self.processes(app))
            self.send(app, targets, signal.SIGTERM)
            if not self.wait_stopped(app, targets, 2):
                self.send(app, targets, signal.SIGKILL)
                if not self.wait_stopped(app, targets, 2):
                    raise RuntimeError('Application did not stop')
            env = os.environ.copy()
            for key in ('APPDIR', 'APPIMAGE', 'ELECTRON_RUN_AS_NODE', 'ELECTRON_NO_ATTACH_CONSOLE'):
                env.pop(key, None)
            log_dir = Path(env.get('HOME', '/config')) / '.local/log'
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / f'weharbor-{app}.log').open('ab') as log:
                child = subprocess.Popen(APPS[app]['command'], env=env,
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                         start_new_session=True)
            self.children[app] = child
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError('Application failed to start')
                if any(main for _, main in self.processes(app).values()):
                    return {'ok': True, 'app': app, 'running': True}
                time.sleep(0.1)
            raise RuntimeError('Application startup timed out')
        finally:
            self.locks[app].release()


def register_routes(application):
    import asyncio
    import logging
    from aiohttp import web

    controller = AppController()

    async def status(_request):
        return web.json_response(controller.status(), headers={'Cache-Control': 'no-store'})

    async def restart(request):
        app = request.match_info['app']
        if app not in APPS:
            raise web.HTTPNotFound()
        if not permitted_request(request.headers, request.host, request.content_type):
            raise web.HTTPForbidden(text='Use a same-origin JSON restart request')
        try:
            result = await asyncio.to_thread(controller.restart, app)
            return web.json_response(result, headers={'Cache-Control': 'no-store'})
        except RestartBusy:
            return web.json_response({'error': '应用正在重启，请稍后再试。'}, status=409)
        except Exception:
            logging.getLogger(__name__).exception('Failed to restart %s', app)
            return web.json_response({'error': '重启失败，请检查应用日志。'}, status=503)

    application.router.add_get('/apps', status)
    application.router.add_post('/apps/{app}/restart', restart)
