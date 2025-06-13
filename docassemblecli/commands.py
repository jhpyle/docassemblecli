import re
import datetime
import shutil
import zipfile
import stat
import tempfile
import time
import sys
import os
import argparse
import yaml
import requests
import subprocess
from packaging import version as packaging_version
from watchdog.observers import Observer
from watchdog.events import RegexMatchingEventHandler
import asyncio
import signal
import hashlib
from pathlib import Path

IGNORE_REGEXES = ['.*/\.git$', '.*/\.git/.*', '.*~$', '.*/\.?\#.*', '.*/\.?flycheck_.*', '.*__pycache__.*', '.*/\.mypy_cache/.*', '.*\.egg-info.*', '.*\.py[cod]$', '.*\$py\.class$', '.*\.swp$', '.*/build/.*', '.*\.tmp$', '.*\#$', '.*/\.~.*', '.*/~.*', '.*\.swx$']
IGNORE_DIRS = ['.git', '__pycache__', '.mypy_cache', '.venv', '.history', 'build']
SETTLE_DELAY = 0.6  # Delay in seconds to let the local system become settled after an event. The optimal value depends on how local applications modify files.

if os.sep == '\\':
    IGNORE_REGEXES = [item.replace('/', '\\\\') for item in IGNORE_REGEXES]

observer = None
full_install_done = False
checksums = {}  # type: ignore[var-annotated]

def checksum_is_same(path):
    path = os.path.abspath(path)
    try:
        with open(path, "rb") as fp:
            new_checksum = hashlib.md5(fp.read()).hexdigest()
        response = checksums.get(path, '') == new_checksum
        checksums[path] = new_checksum
    except FileNotFoundError:
        response = True
    return response

def debug_log(args, message):
    if args.debug:
        sys.stderr.write(message + "\n")

class TerminalException(Exception):
    pass

class GracefulExit(SystemExit):
    code = 1

class WatchHandler(RegexMatchingEventHandler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.BaseEventLoop, data: dict, *args, **kwargs):
        self._loop = loop
        self._queue = queue
        self._data = data
        super().__init__(*args, **kwargs)

    def on_any_event(self, event):
        if event.event_type not in ('opened', 'closed') and not (event.is_directory and event.event_type == 'modified'):
            debug_log(self._data['args'], "Got event " + repr(event.event_type) + " on " + repr(event.src_path))
            invalid = False
            the_path = os.path.abspath(event.src_path)
            for comparison_path in self._data['to_ignore']:
                if the_path.startswith(comparison_path):
                    invalid = True
                    break
            if not invalid:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, {'event_type': event.event_type, 'is_directory': event.is_directory, 'src_path': the_path, 'time': time.time()})

def update_to_do(queue, to_do):
    try:
        while True:
            to_do.append(queue.get_nowait())
    except asyncio.QueueEmpty:
        pass

async def handle_event_after_delay(queue, to_do, data):
    global full_install_done
    await asyncio.sleep(SETTLE_DELAY)
    first_time = True
    something_done = False
    while len(to_do) > 0:
        manual_mode = False
        for event in to_do:
            if event['event_type'] == 'manual':
                manual_mode = True
                first_time = False
                break
        if first_time:
            update_to_do(queue, to_do)
            while time.time() - to_do[-1]['time'] < 0.05:  # If it looks like the events are still coming in, wait and check the queue again
                await asyncio.sleep(0.1)
                update_to_do(queue, to_do)
            try:
                to_do.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                pass
        events_by_type = {}
        for event in to_do:
            if event['src_path'] in events_by_type:
                if event['event_type'] == 'deleted':
                    del events_by_type[event['src_path']]
                else:
                    if 'deleted' in events_by_type[event['src_path']]:
                        del events_by_type[event['src_path']]['deleted']
                        if len(events_by_type[event['src_path']]) == 0:
                            del events_by_type[event['src_path']]
            if event['event_type'] == 'modified' and checksum_is_same(event['src_path']):
                debug_log(data['args'], event['src_path'] + " was not actually changed, or has already been deleted; disregarding.")
                continue
            if event['src_path'] not in events_by_type:
                events_by_type[event['src_path']] = {}
            events_by_type[event['src_path']][event['event_type']] = event
        unduplicated_to_do = []
        for file_path, events in events_by_type.items():
            if 'manual' in events:
                unduplicated_to_do.append(events['manual'])
            elif 'created' in events:
                unduplicated_to_do.append(events['created'])
            elif 'modified' in events:
                unduplicated_to_do.append(events['modified'])
            elif 'deleted' in events:
                unduplicated_to_do.append(events['deleted'])
        if len(unduplicated_to_do) > 0:
            something_done = True
            if not data['args'].norestart and full_install_done and not data['args'].force_restart and not manual_mode:
                # The installation will not trigger a restart unless:
                # 1. A flag specifies that a restart should or should not happen.
                # 2. This is the first install.
                # 3. The installer is triggered manually.
                data['args'].norestart = True
                debug_log(data['args'], "norestart is True initially")
                for event in unduplicated_to_do:
                    debug_log(data['args'], "considering event " + repr(event))
                    if event['event_type'] == 'manual' or event['src_path'].endswith('.py'):
                        debug_log(data['args'], "norestart is now False")
                        data['args'].norestart = False
                        break
            debug_log(data['args'], "not going to restart the server" if data['args'].norestart else "going to restart the server")
            if manual_mode:
                single_file_appropriate = False
            else:
                if not full_install_done:
                    single_file_appropriate = False
                else:
                    single_file_appropriate = data['args'].playground
                    if single_file_appropriate:
                        for event in unduplicated_to_do:
                            if event['src_path'].endswith('.py') and event['event_type'] == 'deleted':
                                single_file_appropriate = False
                                break
                sys.stdout.write("Detected changes to:\n")
                for path in set(item['src_path'][data['trim']:] for item in unduplicated_to_do):
                    sys.stdout.write(f"{path}\n")
                sys.stdout.flush()
            if single_file_appropriate:
                other_files_involved = False
                todo_by_folder = {'questions': set(), 'sources': set(), 'static': set(), 'templates': set(), 'modules': set()}
                for event in unduplicated_to_do:
                    if event['is_directory']:
                        debug_log(data['args'], event['src_path'] + " is a directory, so skipping it")
                        continue
                    if event['event_type'] == 'deleted':
                        debug_log(data['args'], event['src_path'] + " was deleted, so no need to upload anything")
                        if event['src_path'] in checksums:
                            del checksums[event['src_path']]
                        continue
                    path = '/'.join(os.path.normpath(event['src_path']).split(os.sep))
                    m = re.search(r'/docassemble/([^/]+)/data/([^/]+)/', path)
                    if m:
                        if m.group(2) in ('questions', 'sources', 'static', 'templates'):
                            todo_by_folder[m.group(2)].add(event['src_path'])
                    else:
                        m = re.search(r'/docassemble/([^/]+)/([^/]+)\.py$', path)
                        if m:
                            todo_by_folder['modules'].add(event['src_path'])
                        else:
                            other_files_involved = True
                            debug_log(data['args'], event['src_path'] + " changed, so the whole package will be uploaded")
                            break
                if other_files_involved:
                    try:
                        do_install(data['args'], data['apikey'], data['apiurl'], data['to_ignore'])
                    except TerminalException as err:
                        sys.stderr.write("Install failed: " + str(err) + "\n")
                else:
                    for folder in ('questions', 'sources', 'static', 'templates', 'modules'):
                        if len(todo_by_folder[folder]) > 0:
                            debug_log(data['args'], "Uploading " + repr(todo_by_folder[folder]) + " to " + folder)
                            list_of_files = list(todo_by_folder[folder])
                            for file_path in list_of_files:
                                sys.stdout.write("Uploading " + file_path[data['trim']:] + " to " + folder + "\n")
                                sys.stdout.flush()
                                post_data = {'folder': folder, 'restart': '1' if folder == 'modules' and file_path == list_of_files[-1] else '0'}
                                if data['args'].project and data['args'].project != 'default':
                                    post_data['project'] = data['args'].project
                                try:
                                    r = requests.post(data['apiurl'] + '/api/playground', data=post_data, files={'file': open(file_path, 'rb')}, headers={'X-API-Key': data['apikey']}, timeout=50)
                                    if r.status_code == 200:
                                        try:
                                            info = r.json()
                                        except:
                                            raise TerminalException("Server did not return JSON: " + r.text)
                                        task_id = info['task_id']
                                        success = wait_for_server(True, task_id, data['apikey'], data['apiurl'])
                                        if not success:
                                            sys.stderr.write("Failed to upload " + file_path + ". Restart process did not return a success code.\n")
                                    elif r.status_code == 204:
                                        success = True
                                    else:
                                        success = False
                                    if not success:
                                        sys.stderr.write("Failed to upload " + file_path + "\n" + r.text + "\n")
                                except requests.exceptions.Timeout:
                                    sys.stderr.write("Server timed out while uploading " + file_path)
                                except FileNotFoundError:
                                    sys.stderr.write(file_path + " disappeared during processing\n")
            else:
                if manual_mode:
                    important_file_updated = True
                else:
                    important_file_updated = False
                    for event in unduplicated_to_do:
                        if event['is_directory']:
                            debug_log(data['args'], event['src_path'] + " is a directory, so skipping this event")
                        else:
                            important_file_updated = True
                            break
                if important_file_updated:
                    try:
                        if not full_install_done:
                            if manual_mode:
                                sys.stdout.write("Doing an initial upload of the whole package to make sure the current version of the package exists in the Playground. Subsequent uploads will be incremental.\n")
                            sys.stdout.flush()
                        do_install(data['args'], data['apikey'], data['apiurl'], data['to_ignore'])
                        full_install_done = True
                        debug_log(data['args'], "Finished the full install.")
                    except TerminalException as err:
                        sys.stderr.write("Install failed: " + str(err) + "\n")
        debug_log(data['args'], "Starting marking events as handled")
        for event in to_do:  # pylint: disable=unused-variable
            queue.task_done()
        debug_log(data['args'], "Finished marking events as handled")
        to_do = []
        debug_log(data['args'], "Starting seeing if any additional events arrived")
        update_to_do(queue, to_do)
        debug_log(data['args'], "Finished seeing if any additional events arrived")
        first_time = False
    if something_done:
        sys.stdout.write("Done.\n")
        sys.stdout.flush()

async def add_manual_event_to_queue(loop, queue):
    await asyncio.sleep(0.01)
    loop.call_soon_threadsafe(queue.put_nowait, {'event_type': 'manual', 'is_directory': False, 'src_path': '', 'time': time.time()})

async def wait_for_item_in_queue(queue, data):
    while True:
        first_item = await queue.get()
        asyncio.create_task(handle_event_after_delay(queue, [first_item], data))
        await queue.join()

def watch(path: Path, queue: asyncio.Queue, loop: asyncio.BaseEventLoop,
          data: dict, recursive: bool = False) -> None:
    global observer
    handler = WatchHandler(queue, loop, data, ignore_regexes=data['ignore_regexes'])
    observer = Observer()
    observer.schedule(handler, str(path), recursive=recursive)
    observer.start()
    try:
        observer.join()
    finally:
        observer.stop()
        observer.join()
    loop.call_soon_threadsafe(queue.put_nowait, None)


def select_server(env, apiname):
    for item in env:
        if item.get('name', None) == apiname:
            return item
    raise TerminalException("Server " + apiname + " is not present in the .docassemblecli file")


def save_dotfile(dotfile, env):
    try:
        with open(dotfile, 'w', encoding='utf-8') as fp:
            yaml.dump(env, fp)
        os.chmod(dotfile, stat.S_IRUSR | stat.S_IWUSR)
    except Exception as err:
        sys.stderr.write("Unable to save .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err) + "\n")
        return False
    return True


def add_or_update_env(env, apiurl, apikey):
    apiname = name_from_url(apiurl)
    found = False
    for item in env:
        if item.get('name', None) == apiname:
            item['apiurl'] = apiurl
            item['apikey'] = apikey
            found = True
            break
    if not found:
        env.append({'apiurl': apiurl, 'apikey': apikey, 'name': apiname})


def name_from_url(url):
    name = re.sub(r'^https?\:\/\/', '', url)
    name = re.sub(r'/.*', '', name)
    return name


def wait_for_server(playground:bool, task_id, apikey, apiurl):
    if playground:
        sys.stdout.write("Waiting for server to restart.")
    else:
        sys.stdout.write("Waiting for package to install.")
    sys.stdout.flush()
    time.sleep(1)
    sys.stdout.write(".")
    sys.stdout.flush()
    time.sleep(1)
    sys.stdout.write(".")
    sys.stdout.flush()
    time.sleep(1)
    tries = 0
    while tries < 300:
        if playground:
            full_url = apiurl + '/api/restart_status'
        else:
            full_url = apiurl + '/api/package_update_status'
        try:
            r = requests.get(full_url, params={'task_id': task_id}, headers={'X-API-Key': apikey}, timeout=6)
        except requests.exceptions.Timeout:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(2)
            tries += 1
            continue
        if r.status_code != 200:
            raise TerminalException("package_update_status returned " + str(r.status_code) + ": " + r.text)
        info = r.json()
        if info['status'] == 'completed' or info['status'] == 'unknown':
            break
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1)
        tries += 1
    success = False
    if playground:
        if info.get('status', None) == 'completed':
            success = True
    elif info.get('ok', False):
        success = True
    if success:
        return True
    sys.stderr.write("\nUnable to install package.\n")
    if not playground:
        if 'error_message' in info and isinstance(info['error_message'], str):
            sys.stderr.write(info['error_message'] + "\n")
        else:
            sys.stderr.write(repr(info))
            sys.stderr.write("\n")
    sys.stdout.flush()
    return False


def dainstall():
    # global full_install_done
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs='?')
    parser.add_argument("--apiurl", help="base url of your docassemble server, e.g. https://da.example.com")
    parser.add_argument("--apikey", help="docassemble API key")
    parser.add_argument("--norestart", help="do not restart the docassemble server after installing package (only applicable in single-server environments)", action="store_true")
    parser.add_argument("--watch", help="watch the directory for changes and install changes when there is a change", action="store_true")
    parser.add_argument("--force-restart", help="unconditionally restart the docassemble server after installing package", action="store_true")
    parser.add_argument("--server", help="use a particular server from the .docassemblecli config file")
    parser.add_argument("--playground", help="install into your Playground instead of into the server", action="store_true")
    parser.add_argument("--project", help="install into a specific project in the Playground")
    parser.add_argument("--add", help="add another server to the .docassemblecli config file", action="store_true")
    parser.add_argument("--noconfig", help="do not use the .docassemblecli config file", action="store_true")
    parser.add_argument("--debug", help="use verbose logging", action="store_true")
    args = parser.parse_args()
    if args.norestart and args.force_restart:
        return("The --norestart option can cannot be used with --force-restart.")
    if args.project and not args.playground:
        return("The --project option can only be used with --playground.")
    if not args.add:
        if args.directory is None:
            parser.print_help()
            return(1)
        if not os.path.isdir(args.directory):
            return(args.directory + " could not be found.")
        if not (os.path.isfile(os.path.join(args.directory, 'setup.py')) or os.path.isfile(os.path.join(args.directory, 'setup.cfg')) or os.path.isfile(os.path.join(args.directory, 'pyproject.toml'))):
            return(args.directory + " does not contain a setup.py, setup.cfg, or pyproject.toml file, so it is not the directory of a Python package.")
    used_input = False
    if args.noconfig:
        if args.add:
            return("Using --add is not compatible with --noconfig.  Exiting.")
        env = []
    else:
        if os.path.isfile(dotfile):
            try:
                with open(dotfile, 'r', encoding='utf-8') as fp:
                    env = yaml.load(fp, Loader=yaml.FullLoader)
            except Exception as err:
                sys.stderr.write("Unable to load .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err) + "\n")
                env = []
        else:
            env = []
        if isinstance(env, dict) and 'apikey' in env and 'apiurl' in env:
            env['name'] = name_from_url(str(env['apiurl']))
            env = [env]
            used_input = True
        if not isinstance(env, list):
            sys.stderr.write("Format of .docassemblecli file is not a list; ignoring.\n")
            env = []
    if args.add:
        if args.apiurl:
            apiurl = args.apiurl
        else:
            apiurl = input('Base URL of your docassemble server (e.g., https://da.example.com): ').strip()
        if args.apikey:
            apikey = args.apikey
        else:
            apikey = input('API key of admin user on ' + apiurl + ': ').strip()
        add_or_update_env(env, apiurl, apikey)
        if save_dotfile(dotfile, env):
            sys.stdout.write("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl) + "\n")
        return(0)
    if args.server:
        try:
            selected_env = select_server(env, args.server)
        except TerminalException as err:
            return(str(err))
    elif len(env) > 0:
        selected_env = env[0]
    else:
        selected_env = {}
    if args.apiurl:
        apiurl = args.apiurl
    elif 'apiurl' in selected_env and isinstance(selected_env['apiurl'], str):
        apiurl = selected_env['apiurl']
    elif os.environ.get('DOCASSEMBLEAPIURL'):
        apiurl = os.environ.get('DOCASSEMBLEAPIURL')
    else:
        used_input = True
        apiurl = input('Base URL of your docassemble server (e.g., https://da.example.com): ')
    if not re.search(r'^https?://[^\s]+$', apiurl):
        return("Invalid API url " + apiurl)
    apiurl = re.sub(r'/+$', '', apiurl)
    if args.apikey:
        apikey = args.apikey
    elif 'apikey' in selected_env and isinstance(selected_env['apikey'], str):
        apikey = selected_env['apikey']
    elif os.environ.get('DOCASSEMBLEAPIKEY'):
        apikey = os.environ.get('DOCASSEMBLEAPIKEY')
    else:
        used_input = True
        apikey = input('API key of admin user on ' + apiurl + ': ')
    if used_input and not args.noconfig:
        add_or_update_env(env, apiurl, apikey)
        if save_dotfile(dotfile, env):
            sys.stdout.write("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl) + "\n")
    args.directory = re.sub(r'/$', '', args.directory)
    if shutil.which("git") is not None:
        try:
            ignore_process = subprocess.run(['git', 'ls-files', '-i', '--directory', '-o', '--exclude-standard'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, cwd=args.directory, check=False)
            ignore_process.check_returncode()
            raw_ignore = ignore_process.stdout.splitlines()
        except:
            raw_ignore = []
    else:
        raw_ignore = []
    to_ignore = [path.rstrip('/') for path in raw_ignore]
    package_name = os.path.basename(os.path.abspath(args.directory))
    try:
        test_connection(args.playground, apiurl, apikey)
    except Exception as e:
        return("Unable to connect to server. " + str(e))
    if args.watch:
        data = {"args": args, "apikey": apikey, "apiurl": apiurl, "to_ignore": [os.path.abspath(os.path.join(args.directory, item)) for item in to_ignore], 'ignore_regexes': IGNORE_REGEXES, 'trim': 1 + len(os.path.abspath(args.directory))}
        # if args.playground:
        #     sys.stdout.write("Doing an initial upload of " + package_name + " to make sure the package is uploaded to the Playground. Subsequent uploads will be incremental.\n")
        #     do_install(data['args'], data['apikey'], data['apiurl'], data['to_ignore'])
        #     full_install_done = True
        sys.stdout.write("Watching " + package_name + " for changes.\n")
        loop = asyncio.get_event_loop()
        queue = asyncio.Queue()
        futures = [
            loop.run_in_executor(None, watch, Path(args.directory), queue, loop, data, True),
            wait_for_item_in_queue(queue, data),
        ]
        if args.playground:
            futures.append(add_manual_event_to_queue(loop, queue))
        main_task = asyncio.gather(*futures)
        def raise_graceful_exit(*args):  # pylint: disable=unused-argument
            sys.stdout.write("\nExiting\n")
            main_task.cancel()
            raise GracefulExit()
        signal.signal(signal.SIGINT, raise_graceful_exit)
        signal.signal(signal.SIGTERM, raise_graceful_exit)
        try:
            loop.run_until_complete(main_task)
        except (asyncio.CancelledError, GracefulExit):
            if observer is not None:
                observer.stop()
            loop.close()
        sys.stdout.write("\n")
        return(0)
    try:
        do_install(args, apikey, apiurl, to_ignore)
    except TerminalException as err:
        return(str(err))
    return(0)


def dauninstall():
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
    parser = argparse.ArgumentParser()
    parser.add_argument("package")
    parser.add_argument("--apiurl", help="base url of your docassemble server, e.g. https://da.example.com")
    parser.add_argument("--apikey", help="docassemble API key")
    parser.add_argument("--norestart", help="do not restart the docassemble server after installing package (only applicable in single-server environments)", action="store_true")
    parser.add_argument("--server", help="use a particular server from the .docassemblecli config file")
    parser.add_argument("--noconfig", help="do not use the .docassemblecli config file", action="store_true")
    parser.add_argument("--debug", help="use verbose logging", action="store_true")
    args = parser.parse_args()
    used_input = False
    if args.noconfig:
        env = []
    else:
        if os.path.isfile(dotfile):
            try:
                with open(dotfile, 'r', encoding='utf-8') as fp:
                    env = yaml.load(fp, Loader=yaml.FullLoader)
            except Exception as err:
                sys.stderr.write("Unable to load .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err) + "\n")
                env = []
        else:
            env = []
        if isinstance(env, dict) and 'apikey' in env and 'apiurl' in env:
            env['name'] = name_from_url(str(env['apiurl']))
            env = [env]
            used_input = True
        if not isinstance(env, list):
            sys.stderr.write("Format of .docassemblecli file is not a list; ignoring.\n")
            env = []
    if args.server:
        try:
            selected_env = select_server(env, args.server)
        except TerminalException as err:
            return(str(err))
    elif len(env) > 0:
        selected_env = env[0]
    else:
        selected_env = {}
    if args.apiurl:
        apiurl = args.apiurl
    elif 'apiurl' in selected_env and isinstance(selected_env['apiurl'], str):
        apiurl = selected_env['apiurl']
    elif os.environ.get('DOCASSEMBLEAPIURL'):
        apiurl = os.environ.get('DOCASSEMBLEAPIURL')
    else:
        used_input = True
        apiurl = input('Base URL of your docassemble server (e.g., https://da.example.com): ')
    if not re.search(r'^https?://[^\s]+$', apiurl):
        return("Invalid API url " + apiurl)
    apiurl = re.sub(r'/+$', '', apiurl)
    if args.apikey:
        apikey = args.apikey
    elif 'apikey' in selected_env and isinstance(selected_env['apikey'], str):
        apikey = selected_env['apikey']
    elif os.environ.get('DOCASSEMBLEAPIKEY'):
        apikey = os.environ.get('DOCASSEMBLEAPIKEY')
    else:
        used_input = True
        apikey = input('API key of admin user on ' + apiurl + ': ')
    if used_input and not args.noconfig:
        add_or_update_env(env, apiurl, apikey)
        if save_dotfile(dotfile, env):
            sys.stdout.write("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl) + "\n")
    try:
        test_connection(False, apiurl, apikey)
    except Exception as e:
        return("Unable to connect to server. " + str(e))
    data = {'package': args.package}
    if args.norestart:
        data['restart'] = '0'
    try:
        r = requests.delete(apiurl + '/api/package', params=data, headers={'X-API-Key': apikey}, timeout=50)
        if r.status_code != 200:
            raise TerminalException("package DELETE returned " + str(r.status_code) + ": " + r.text)
        info = r.json()
        task_id = info['task_id']
        if wait_for_server(False, task_id, apikey, apiurl):
            sys.stdout.write("\nUninstalled.\n")
    except TerminalException as err:
        return(str(err))
    return(0)

def test_connection(playground, apiurl, apikey):
    general_test_response = requests.get(apiurl + '/api/package', headers={'X-API-Key': apikey}, timeout=50)
    if general_test_response.status_code == 403:
        raise Exception(f"Please verify the validity of your API-Key.")
    elif general_test_response.status_code != 200:
        raise Exception(f"Server responded with status code {general_test_response.status_code}.")
    if not playground:
        return
    playground_test_response = requests.get(apiurl + '/api/playground/project', headers={'X-API-Key': apikey}, timeout=50)
    if playground_test_response.status_code != 200:
        raise Exception("Please check if 'enable playground' is set to 'True' in servers configuration.")
    return

def do_install(args, apikey, apiurl, to_ignore):
    archive = tempfile.NamedTemporaryFile(suffix=".zip")
    zf = zipfile.ZipFile(archive, compression=zipfile.ZIP_DEFLATED, mode='w')
    root_directory = None
    has_python_files = False
    this_package_name = None
    dependencies = {}
    for root, dirs, files in os.walk(args.directory, topdown=True):
        adjusted_root = os.sep.join(root.split(os.sep)[1:])
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('flycheck_') and not d.endswith('.egg-info') and os.path.join(adjusted_root, d) not in to_ignore]
        if root_directory is None and ('setup.py' in files or 'setup.cfg' in files or 'pyproject.toml' in files):
            root_directory = root
            if 'setup.py' in files:
                with open(os.path.join(root, 'setup.py'), 'r', encoding='utf-8') as fp:
                    setup_text = fp.read()
                    m = re.search(r'setup\(.*\bname=(["\'])(.*?)(["\'])', setup_text)
                    if m and m.group(1) == m.group(3):
                        this_package_name = m.group(2).strip()
                    m = re.search(r'setup\(.*install_requires=\[(.*?)\]', setup_text, flags=re.DOTALL)
                    if m:
                        for package_text in m.group(1).split(','):
                            package_name = package_text.strip()
                            if len(package_name) >= 3 and package_name[0] == package_name[-1] and package_name[0] in ("'", '"'):
                                package_name = package_name[1:-1]
                                mm = re.search(r'(.*)(<=|>=|==|<|>)(.*)', package_name)
                                if mm:
                                    dependencies[mm.group(1).strip()] = {'installed': False, 'operator': mm.group(2), 'version': mm.group(3).strip()}
                                else:
                                    dependencies[package_name] = {'installed': False, 'operator': None, 'version': None}
        for the_file in files:
            if the_file.endswith('~') or the_file.endswith('.pyc') or the_file.endswith('.swp') or the_file.startswith('#') or the_file.startswith('.#') or the_file.startswith('.flycheck_') or (the_file == '.gitignore' and root_directory == root) or os.path.join(adjusted_root, the_file) in to_ignore:
                continue
            if not has_python_files and the_file.endswith('.py') and not (the_file in ('setup.py', 'setup.cfg', 'pyproject.toml') and root == root_directory) and the_file != '__init__.py':
                has_python_files = True
            if args.watch:
                checksum_is_same(os.path.join(root, the_file))
            zf.write(os.path.join(root, the_file), os.path.relpath(os.path.join(root, the_file), os.path.join(args.directory, '..')))
    zf.close()
    archive.seek(0)
    if args.norestart:
        should_restart = False
    elif args.force_restart or has_python_files:
        should_restart = True
    elif len(dependencies) > 0 or this_package_name:
        r = requests.get(apiurl + '/api/package', headers={'X-API-Key': apikey}, timeout=50)
        if r.status_code != 200:
            raise TerminalException("/api/package returned " + str(r.status_code) + ": " + r.text)
        installed_packages = r.json()
        already_installed = False
        for package_info in installed_packages:
            package_info['alt_name'] = re.sub('^docassemble\.', 'docassemble-', package_info['name'])
            for dependency_name, dependency_info in dependencies.items():
                if dependency_name in (package_info['name'], package_info['alt_name']):
                    condition = True
                    if dependency_info['operator']:
                        if dependency_info['operator'] == '==':
                            condition = packaging_version.parse(package_info['version']) == packaging_version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '<=':
                            condition = packaging_version.parse(package_info['version']) <= packaging_version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '>=':
                            condition = packaging_version.parse(package_info['version']) >= packaging_version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '<':
                            condition = packaging_version.parse(package_info['version']) < packaging_version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '>':
                            condition = packaging_version.parse(package_info['version']) > packaging_version.parse(dependency_info['version'])
                    if condition:
                        dependency_info['installed'] = True
            if this_package_name and this_package_name in (package_info['name'], package_info['alt_name']):
                already_installed = True
        should_restart = bool((not already_installed and len(dependencies) > 0) or not all(item['installed'] for item in dependencies.values()))
    else:
        should_restart = True
    data = {}
    if not should_restart:
        data['restart'] = '0'
    if args.playground:
        if args.project and args.project != 'default':
            data['project'] = args.project
        project_endpoint = apiurl + '/api/playground/project'
        project_list = requests.get(project_endpoint, headers={'X-API-Key': apikey}, timeout=50)
        if project_list.status_code == 200:
            if not args.project in project_list:
                try:
                    requests.post(project_endpoint, data={'project': args.project}, headers={'X-API-Key': apikey}, timeout=50)
                except:
                    raise TerminalException("create project POST failed")
        else:
            sys.stdout.write("\n")
            raise TerminalException("playground list of projects GET returned " + str(project_list.status_code) + ": " + project_list.text)
        r = requests.post(apiurl + '/api/playground_install', data=data, files={'file': archive}, headers={'X-API-Key': apikey}, timeout=50)
        if r.status_code == 400:
            try:
                error_message = r.json()
            except:
                error_message = ''
            if 'project' not in data or error_message != 'Invalid project.':
                raise TerminalException('playground_install POST returned ' + str(r.status_code) + ": " + r.text)
            r = requests.post(apiurl + '/api/playground/project', data={'project': data['project']}, headers={'X-API-Key': apikey}, timeout=50)
            if r.status_code != 204:
                raise TerminalException("needed to create playground project but POST to api/playground/project returned " + str(r.status_code) + ": " + r.text)
            archive.seek(0)
            r = requests.post(apiurl + '/api/playground_install', data=data, files={'file': archive}, headers={'X-API-Key': apikey}, timeout=50)
        if r.status_code == 200:
            try:
                info = r.json()
            except:
                raise TerminalException(r.text)
            task_id = info['task_id']
            success = wait_for_server(args.playground, task_id, apikey, apiurl)
        elif r.status_code == 204:
            success = True
        else:
            sys.stdout.write("\n")
            raise TerminalException("playground_install POST returned " + str(r.status_code) + ": " + r.text)
        if success:
            sys.stdout.write("\nInstalled.\n")
            sys.stdout.flush()
        else:
            raise TerminalException("\nInstall failed\n")
    else:
        r = requests.post(apiurl + '/api/package', data=data, files={'zip': archive}, headers={'X-API-Key': apikey}, timeout=50)
        if r.status_code != 200:
            raise TerminalException("package POST returned " + str(r.status_code) + ": " + r.text)
        info = r.json()
        task_id = info['task_id']
        if wait_for_server(args.playground, task_id, apikey, apiurl):
            sys.stdout.write("\nInstalled.\n")
        if not should_restart:
            r = requests.post(apiurl + '/api/clear_cache', headers={'X-API-Key': apikey}, timeout=50)
            if r.status_code != 204:
                raise TerminalException("clear_cache returned " + str(r.status_code) + ": " + r.text)


def dacreate():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", help="name of the package you want to create", nargs='?')
    parser.add_argument("--developer-name", help="name of the developer of the package")
    parser.add_argument("--developer-email", help="email of the developer of the package")
    parser.add_argument("--description", help="description of package")
    parser.add_argument("--url", help="URL of package")
    parser.add_argument("--license", help="license of package")
    parser.add_argument("--version", help="version number of package")
    parser.add_argument("--output", help="output directory in which to create the package")
    args = parser.parse_args()
    pkgname = args.package
    if not pkgname:
        pkgname = input('Name of the package you want to create (e.g., childsupport): ')
    pkgname = re.sub(r'\s', '', pkgname)
    if not pkgname:
        return("The package name you entered is invalid.")
    pkgname = re.sub(r'^docassemble[\-\.]', '', pkgname, flags=re.IGNORECASE)
    if args.output:
        packagedir = args.output
    else:
        packagedir = 'docassemble-' + pkgname
    if os.path.exists(packagedir):
        if not os.path.isdir(packagedir):
            return("Cannot create the directory " + packagedir + " because the path already exists.")
        dir_listing = list(os.listdir(packagedir))
        if 'setup.py' in dir_listing or 'setup.cfg' in dir_listing or 'pyproject.toml' in dir_listing:
            return("The directory " + packagedir + " already has a package in it.")
    else:
        os.makedirs(packagedir, exist_ok=True)
    developer_name = args.developer_name
    if not developer_name:
        developer_name = input('Name of developer: ').strip()
        if not developer_name:
            developer_name = "Your Name Here"
    developer_email = args.developer_email
    if not developer_email:
        developer_email = input('Email address of developer [developer@example.com]: ').strip()
        if not developer_email:
            developer_email = "developer@example.com"
    description = args.description
    if not description:
        description = input('Description of package [A docassemble extension]: ').strip()
        if not description:
            description = "A docassemble extension."
    package_url = args.url
    if not package_url:
        package_url = input('URL of package [https://docassemble.org]: ').strip()
        if not package_url:
            package_url = "https://docassemble.org"
    license_txt = args.license
    if not license_txt:
        license_txt = input('License of package [MIT]: ').strip()
        if not license_txt:
            license_txt = "MIT"
    version = args.version
    if not version:
        version = input('Version of package [0.0.1]: ').strip()
        if not version:
            version = "0.0.1"
    initpy = """\
__import__('pkg_resources').declare_namespace(__name__)

"""
    if 'MIT' in license_txt:
        license_content = 'The MIT License (MIT)\n\nCopyright (c) ' + str(datetime.datetime.now().year) + ' ' + developer_name + """

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    else:
        license_content = license_txt + "\n"
    gitignore = """\
__pycache__/
*.py[cod]
*$py.class
.mypy_cache/
.dmypy.json
dmypy.json
*.egg-info/
.installed.cfg
*.egg
.vscode
*~
.#*
en
*/auto
.history/
.idea
.dir-locals.el
.flake8
*.swp
*.tmp
.DS_Store
.envrc
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
"""
    readme = '# docassemble.' + pkgname + "\n\n" + description + "\n\n## Author\n\n" + developer_name + ", " + developer_email + "\n"
    manifestin = """\
include README.md
"""
    setupcfg = """\
[metadata]
description_file = README.md
"""
    setuppy = """\
import os
import sys
from setuptools import setup, find_packages
from fnmatch import fnmatchcase
from distutils.util import convert_path

standard_exclude = ('*.pyc', '*~', '.*', '*.bak', '*.swp*')
standard_exclude_directories = ('.*', 'CVS', '_darcs', './build', './dist', 'EGG-INFO', '*.egg-info')

def find_package_data(where='.', package='', exclude=standard_exclude, exclude_directories=standard_exclude_directories):
    out = {}
    stack = [(convert_path(where), '', package)]
    while stack:
        where, prefix, package = stack.pop(0)
        for name in os.listdir(where):
            fn = os.path.join(where, name)
            if os.path.isdir(fn):
                bad_name = False
                for pattern in exclude_directories:
                    if (fnmatchcase(name, pattern)
                        or fn.lower() == pattern.lower()):
                        bad_name = True
                        break
                if bad_name:
                    continue
                if os.path.isfile(os.path.join(fn, '__init__.py')):
                    if not package:
                        new_package = name
                    else:
                        new_package = package + '.' + name
                        stack.append((fn, '', new_package))
                else:
                    stack.append((fn, prefix + name + '/', package))
            else:
                bad_name = False
                for pattern in exclude:
                    if (fnmatchcase(name, pattern)
                        or fn.lower() == pattern.lower()):
                        bad_name = True
                        break
                if bad_name:
                    continue
                out.setdefault(package, []).append(prefix+name)
    return out

"""
    setuppy += "setup(name=" + repr('docassemble.' + pkgname) + """,
      version=""" + repr(version) + """,
      description=(""" + repr(description) + """),
      long_description=""" + repr(readme) + """,
      long_description_content_type='text/markdown',
      author=""" + repr(developer_name) + """,
      author_email=""" + repr(developer_email) + """,
      license=""" + repr(license_txt) + """,
      url=""" + repr(package_url) + """,
      packages=find_packages(),
      namespace_packages=['docassemble'],
      install_requires=[],
      zip_safe=False,
      package_data=find_package_data(where='docassemble/""" + pkgname + """/', package='docassemble.""" + pkgname + """'),
     )
"""
    questionsdir = os.path.join(packagedir, 'docassemble', pkgname, 'data', 'questions')
    templatesdir = os.path.join(packagedir, 'docassemble', pkgname, 'data', 'templates')
    staticdir = os.path.join(packagedir, 'docassemble', pkgname, 'data', 'static')
    sourcesdir = os.path.join(packagedir, 'docassemble', pkgname, 'data', 'sources')
    if not os.path.isdir(questionsdir):
        os.makedirs(questionsdir, exist_ok=True)
    if not os.path.isdir(templatesdir):
        os.makedirs(templatesdir, exist_ok=True)
    if not os.path.isdir(staticdir):
        os.makedirs(staticdir, exist_ok=True)
    if not os.path.isdir(sourcesdir):
        os.makedirs(sourcesdir, exist_ok=True)
    with open(os.path.join(packagedir, '.gitignore'), 'w', encoding='utf-8') as the_file:
        the_file.write(gitignore)
    with open(os.path.join(packagedir, 'README.md'), 'w', encoding='utf-8') as the_file:
        the_file.write(readme)
    with open(os.path.join(packagedir, 'LICENSE'), 'w', encoding='utf-8') as the_file:
        the_file.write(license_content)
    with open(os.path.join(packagedir, 'setup.py'), 'w', encoding='utf-8') as the_file:
        the_file.write(setuppy)
    with open(os.path.join(packagedir, 'setup.cfg'), 'w', encoding='utf-8') as the_file:
        the_file.write(setupcfg)
    with open(os.path.join(packagedir, 'MANIFEST.in'), 'w', encoding='utf-8') as the_file:
        the_file.write(manifestin)
    with open(os.path.join(packagedir, 'docassemble', '__init__.py'), 'w', encoding='utf-8') as the_file:
        the_file.write(initpy)
    with open(os.path.join(packagedir, 'docassemble', pkgname, '__init__.py'), 'w', encoding='utf-8') as the_file:
        the_file.write("__version__ = " + repr(version) + "\n")
    return(0)

def dadownload():
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
    parser = argparse.ArgumentParser()
    parser.add_argument("package", nargs='?')
    parser.add_argument("--overwrite", help="overwrite existing files", action="store_true")
    parser.add_argument("--apiurl", help="base url of your docassemble server, e.g. https://da.example.com")
    parser.add_argument("--apikey", help="docassemble API key")
    parser.add_argument("--server", help="use a particular server from the .docassemblecli config file")
    parser.add_argument("--playground", help="download from the Playground", action="store_true")
    parser.add_argument("--project", help="download from a specific project in the Playground")
    parser.add_argument("--add", help="add another server to the .docassemblecli config file", action="store_true")
    parser.add_argument("--noconfig", help="do not use the .docassemblecli config file", action="store_true")
    args = parser.parse_args()
    if args.project and not args.playground:
        return("The --project option can only be used with --playground.")
    if not args.add:
        if args.package is None:
            parser.print_help()
            return(1)
    used_input = False
    if args.noconfig:
        if args.add:
            return("Using --add is not compatible with --noconfig.  Exiting.")
        env = []
    else:
        if os.path.isfile(dotfile):
            try:
                with open(dotfile, 'r', encoding='utf-8') as fp:
                    env = yaml.load(fp, Loader=yaml.FullLoader)
            except Exception as err:
                sys.stderr.write("Unable to load .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err) + "\n")
                env = []
        else:
            env = []
        if isinstance(env, dict) and 'apikey' in env and 'apiurl' in env:
            env['name'] = name_from_url(str(env['apiurl']))
            env = [env]
            used_input = True
        if not isinstance(env, list):
            sys.stderr.write("Format of .docassemblecli file is not a list; ignoring.\n")
            env = []
    if args.add:
        if args.apiurl:
            apiurl = args.apiurl
        else:
            apiurl = input('Base URL of your docassemble server (e.g., https://da.example.com): ').strip()
        if args.apikey:
            apikey = args.apikey
        else:
            apikey = input('API key of admin user on ' + apiurl + ': ').strip()
        add_or_update_env(env, apiurl, apikey)
        if save_dotfile(dotfile, env):
            sys.stdout.write("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl) + "\n")
        return(0)
    if args.server:
        try:
            selected_env = select_server(env, args.server)
        except TerminalException as err:
            return(str(err))
    elif len(env) > 0:
        selected_env = env[0]
    else:
        selected_env = {}
    if args.apiurl:
        apiurl = args.apiurl
    elif 'apiurl' in selected_env and isinstance(selected_env['apiurl'], str):
        apiurl = selected_env['apiurl']
    elif os.environ.get('DOCASSEMBLEAPIURL'):
        apiurl = os.environ.get('DOCASSEMBLEAPIURL')
    else:
        used_input = True
        apiurl = input('Base URL of your docassemble server (e.g., https://da.example.com): ')
    if not re.search(r'^https?://[^\s]+$', apiurl):
        return("Invalid API url " + apiurl)
    apiurl = re.sub(r'/+$', '', apiurl)
    if args.apikey:
        apikey = args.apikey
    elif 'apikey' in selected_env and isinstance(selected_env['apikey'], str):
        apikey = selected_env['apikey']
    elif os.environ.get('DOCASSEMBLEAPIKEY'):
        apikey = os.environ.get('DOCASSEMBLEAPIKEY')
    else:
        used_input = True
        apikey = input('API key of admin user on ' + apiurl + ': ')
    if used_input and not args.noconfig:
        add_or_update_env(env, apiurl, apikey)
        if save_dotfile(dotfile, env):
            sys.stdout.write("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl) + "\n")
    package_name = re.sub(r'^docassemble-', 'docassemble.', args.package)
    if not package_name.startswith('docassemble.'):
        package_name = 'docassemble.' + package_name
    package_file_name = re.sub(r'docassemble\.', 'docassemble-', package_name)
    archive = tempfile.NamedTemporaryFile(suffix=".zip")
    if args.playground:
        params = {'folder': 'packages', 'filename': package_name}
        if args.project:
            params['project'] = args.project
        try:
            with requests.get(apiurl + '/api/playground', params=params, stream=True, timeout=60, headers={'X-API-Key': apikey}) as r:
                if r.status_code == 404:
                    return("Package not found.")
                r.raise_for_status()
                with open(archive.name, 'wb') as fp:
                    for chunk in r.iter_content(8192):
                        fp.write(chunk)
        except requests.exceptions.HTTPError as err:
            return("Error downloading package: " + str(err))
    else:
        zip_file_number = None
        found = False
        try:
            response = requests.get(apiurl + '/api/package', headers={'X-API-Key': apikey}, timeout=50)
            assert response.status_code == 200
        except:
            return("Unable to connect to server.")
        for item in response.json():
            if item['name'] == package_name:
                found = True
                if 'zip_file_number' in item:
                    zip_file_number = item['zip_file_number']
                break
        if found is False:
            return("Package not installed.")
        if zip_file_number is None:
            return("Package installed but is not downloadable.")
        try:
            with requests.get(apiurl + '/api/file/' + str(zip_file_number), stream=True, timeout=60, headers={'X-API-Key': apikey}) as r:
                r.raise_for_status()
                with open(archive.name, 'wb') as fp:
                    for chunk in r.iter_content(8192):
                        fp.write(chunk)
        except requests.exceptions.HTTPError as err:
            sys.exit("Error downloading package: " + str(err))
    with zipfile.ZipFile(archive.name, mode='r') as zf:
        if not args.overwrite:
            for file_info in zf.infolist():
                file_path = file_info.filename
                if os.path.exists(file_path):
                    return(f"Unpacking the package here would overwrite existing files ({file_path}). Use --overwrite if you want to overwrite existing files.")
        for file_info in zf.infolist():
            file_path = file_info.filename
            try:
                zf.extract(file_info, path=os.getcwd())
            except Exception as e:
                print(f"Error extracting '{file_path}': {e}")
    print(f"Unpacked {package_file_name}.")
    return(0)
