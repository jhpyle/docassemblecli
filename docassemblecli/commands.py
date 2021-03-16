import sys
import os
import argparse
import yaml
import re
import zipfile
import requests
import stat
import tempfile
import time

def select_server(env, apiname):
    for item in env:
        if item.get('name', None) == apiname:
            return item
    sys.exit("Server " + apiname + " is not present in the .docassemblecli file")

def save_dotfile(dotfile, env):
    try:
        with open(dotfile, 'w', encoding='utf-8') as fp:
            yaml.dump(env, fp)
        os.chmod(dotfile, stat.S_IRUSR | stat.S_IWUSR)
    except Exception as err:
        print("Unable to save .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err))
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

def dainstall():
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs='?')
    parser.add_argument("--apiurl", help="base url of your docassemble server, e.g. https://da.example.com")
    parser.add_argument("--apikey", help="docassemble API key")
    parser.add_argument("--norestart", help="do not restart the docassemble server after installing package (only applicable in single-server environments)", action="store_true")
    parser.add_argument("--server", help="use a particular server from the .docassemblecli config file")
    parser.add_argument("--playground", help="install into your Playground instead of into the server", action="store_true")
    parser.add_argument("--project", help="install into a specific project in the Playground")
    parser.add_argument("--add", help="add another server to the .docassemblecli config file", action="store_true")
    parser.add_argument("--noconfig", help="do not use the .docassemblecli config file", action="store_true")
    args = parser.parse_args()
    if args.project and not args.playground:
        sys.exit("The --project option can only be used with --playground.")
    if not args.add:
        if args.directory is None:
            parser.print_help()
            sys.exit(1)
        if not os.path.isdir(args.directory):
            sys.exit(args.directory + " could not be found.")
        if not os.path.isfile(os.path.join(args.directory, 'setup.py')):
            sys.exit(args.directory + " does not contain a setup.py file, so it is not the directory of a Python package.")
    used_input = False
    if args.noconfig:
        if args.add:
            sys.exit("Using --add is not compatible with --noconfig.  Exiting.")
        env = list()
    else:
        if os.path.isfile(dotfile):
            try:
                with open(dotfile, 'r', encoding='utf-8') as fp:
                    env = yaml.load(fp, Loader=yaml.FullLoader)
            except Exception as err:
                print("Unable to load .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err))
                env = list()
        else:
            env = list()
        if isinstance(env, dict) and 'apikey' in env and 'apiurl' in env:
            env['name'] = name_from_url(str(env['apiurl']))
            env = [env]
            used_input = True
        if not isinstance(env, list):
            print("Format of .docassemblecli file is not a list; ignoring.")
            env = list()
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
            print("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl))
        sys.exit(0)
    if args.server:
        selected_env = select_server(env, args.server)
    elif len(env):
        selected_env = env[0]
    else:
        selected_env = dict()
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
        sys.exit("Invalid API url " + apiurl)
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
            print("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl))
    archive = tempfile.NamedTemporaryFile(suffix=".zip")
    zf = zipfile.ZipFile(archive, mode='w')
    for root, dirs, files in os.walk(args.directory, topdown=True):
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__'] and not d.endswith('.egg-info')]
        for file in files:
            if file.endswith('~') or file.endswith('.pyc') or file.startswith('#') or file.startswith('.#') or file == '.gitignore':
                continue
            zf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), os.path.join(args.directory, '..')))
    zf.close()
    archive.seek(0)
    data = dict()
    if args.norestart:
        data['restart'] = '0'
    if args.playground:
        if args.project and args.project != 'default':
            data['project'] = args.project
        sys.stdout.write("Waiting for package to install.")
        r = requests.post(apiurl + '/api/playground_install', data=data, files={'file': archive}, headers={'X-API-Key': apikey})
        if r.status_code != 204:
            sys.stdout.write("\n")
            sys.exit("playground_install POST returned " + str(r.status_code) + ": " + r.text)
        if args.norestart:
            sys.stdout.write("\nInstalled.\n")
        else:
            sys.stdout.write("\nInstalled. The server may now be restarting.\n")
    else:
        r = requests.post(apiurl + '/api/package', data=data, files={'zip': archive}, headers={'X-API-Key': apikey})
        if r.status_code != 200:
            sys.exit("package POST returned " + str(r.status_code) + ": " + r.text)
        info = r.json()
        task_id = info['task_id']
        sys.stdout.write("Waiting for package to install.")
        sys.stdout.flush()
        time.sleep(1)
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1)
        tries = 0
        while tries < 100:
            r = requests.get(apiurl + '/api/package_update_status', params={'task_id': task_id}, headers={'X-API-Key': apikey})
            if r.status_code != 200:
                sys.exit("package_update_status returned " + str(r.status_code) + ": " + r.text)
            info = r.json()
            if info['status'] == 'completed':
                break
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(1)
            tries += 1
        if info.get('ok', False):
            sys.stdout.write("\nInstalled.\n")
            sys.stdout.flush()
        else:
            sys.stdout.write("\nUnable to install package.\n")
            sys.stdout.flush()
            if 'error_message' in info and isinstance(info['error_message'], str):
                print(info['error_message'])
        if args.norestart:
            r = requests.post(apiurl + '/api/clear_cache', headers={'X-API-Key': apikey})
            if r.status_code != 204:
                sys.exit("clear_cache returned " + str(r.status_code) + ": " + r.text)
    sys.exit(0)
