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

def dainstall():
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--apiurl", help="base url of your docassemble server, e.g. https://da.example.com")
    parser.add_argument("--apikey", help="docassemble API key")
    parser.add_argument("--norestart", help="do not restart the docassemble server after installing package (only applicable in single-server environments)", action="store_true")
    parser.add_argument("--noconfig", help="do not use the .docassemblecli config file", action="store_true")
    args = parser.parse_args()
    if not os.path.isdir(args.directory):
        sys.exit(args.directory + " could not be found.")
    if not os.path.isfile(os.path.join(args.directory, 'setup.py')):
        sys.exit(args.directory + " does not contain a setup.py file, so it is not the directory of a Python package.")
    if args.noconfig:
        env = dict()
    else:
        if os.path.isfile(dotfile):
            try:
                with open(dotfile, 'r', encoding='utf-8') as fp:
                    env = yaml.load(fp, Loader=yaml.FullLoader)
            except Exception as err:
                print("Unable to load .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err))
                env = dict()
        else:
            env = dict()
        if not isinstance(env, dict):
            print("Format of .docassemblecli file is not a dictionary; ignoring.")
            env = dict()
    used_input = False
    if args.apiurl:
        apiurl = args.apiurl
    elif 'apiurl' in env and isinstance(env['apiurl'], str):
        apiurl = env['apiurl']
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
    elif 'apikey' in env and isinstance(env['apikey'], str):
        apikey = env['apikey']
    elif os.environ.get('DOCASSEMBLEAPIKEY'):
        apikey = os.environ.get('DOCASSEMBLEAPIKEY')
    else:
        used_input = True
        apikey = input('API key of admin user on ' + apiurl + ': ')
    if used_input and not args.noconfig:
        env['apiurl'] = apiurl
        env['apikey'] = apikey
        try:
            with open(dotfile, 'w', encoding='utf-8') as fp:
                yaml.dump(env, fp)
            os.chmod(dotfile, stat.S_IRUSR | stat.S_IWUSR)
            print("Saved base URL and API key to .docassemblecli")
        except Exception as err:
            print("Unable to save .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err))
    archive = tempfile.NamedTemporaryFile(suffix=".zip")
    zf = zipfile.ZipFile(archive.name, mode='w')
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
