import re
import datetime
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
from packaging import version


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


def wait_for_server(playground:bool, task_id, apikey, apiurl):
    sys.stdout.write("Waiting for package to install.")
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
        r = requests.get(full_url, params={'task_id': task_id}, headers={'X-API-Key': apikey})
        if r.status_code != 200:
            sys.exit("package_update_status returned " + str(r.status_code) + ": " + r.text)
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
    sys.stdout.write("\nUnable to install package.\n")
    if not playground:
        if 'error_message' in info and isinstance(info['error_message'], str):
            print(info['error_message'])
        else:
            print(info)
    sys.stdout.flush()
    return False


def dainstall():
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs='?')
    parser.add_argument("--apiurl", help="base url of your docassemble server, e.g. https://da.example.com")
    parser.add_argument("--apikey", help="docassemble API key")
    parser.add_argument("--norestart", help="do not restart the docassemble server after installing package (only applicable in single-server environments)", action="store_true")
    parser.add_argument("--force-restart", help="unconditionally restart the docassemble server after installing package", action="store_true")
    parser.add_argument("--server", help="use a particular server from the .docassemblecli config file")
    parser.add_argument("--playground", help="install into your Playground instead of into the server", action="store_true")
    parser.add_argument("--project", help="install into a specific project in the Playground")
    parser.add_argument("--add", help="add another server to the .docassemblecli config file", action="store_true")
    parser.add_argument("--noconfig", help="do not use the .docassemblecli config file", action="store_true")
    args = parser.parse_args()
    if args.norestart and args.force_restart:
        sys.exit("The --norestart option can cannot be used with --force-restart.")
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
        env = []
    else:
        if os.path.isfile(dotfile):
            try:
                with open(dotfile, 'r', encoding='utf-8') as fp:
                    env = yaml.load(fp, Loader=yaml.FullLoader)
            except Exception as err:
                print("Unable to load .docassemblecli file.  " + err.__class__.__name__ + ": " + str(err))
                env = []
        else:
            env = []
        if isinstance(env, dict) and 'apikey' in env and 'apiurl' in env:
            env['name'] = name_from_url(str(env['apiurl']))
            env = [env]
            used_input = True
        if not isinstance(env, list):
            print("Format of .docassemblecli file is not a list; ignoring.")
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
            print("Saved base URL and API key to .docassemblecli as server " + name_from_url(apiurl))
        sys.exit(0)
    if args.server:
        selected_env = select_server(env, args.server)
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
    zf = zipfile.ZipFile(archive, compression=zipfile.ZIP_DEFLATED, mode='w')
    args.directory = re.sub(r'/$', '', args.directory)
    try:
        ignore_process = subprocess.run(['git', 'ls-files', '-i', '--directory', '-o', '--exclude-standard'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, cwd=args.directory)
        ignore_process.check_returncode()
        raw_ignore = ignore_process.stdout.splitlines()
    except:
        raw_ignore = []
    to_ignore = [path.rstrip('/') for path in raw_ignore]
    root_directory = None
    has_python_files = False
    this_package_name = None
    dependencies = {}
    for root, dirs, files in os.walk(args.directory, topdown=True):
        adjusted_root = os.sep.join(root.split(os.sep)[1:])
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.mypy_cache', '.venv', '.history', 'build'] and not d.endswith('.egg-info') and os.path.join(adjusted_root, d) not in to_ignore]
        if root_directory is None and ('setup.py' in files or 'setup.cfg' in files):
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
            if the_file.endswith('~') or the_file.endswith('.pyc') or the_file.startswith('#') or the_file.startswith('.#') or (the_file == '.gitignore' and root_directory == root) or os.path.join(adjusted_root, the_file) in to_ignore:
                continue
            if not has_python_files and the_file.endswith('.py') and not (the_file == 'setup.py' and root == root_directory) and the_file != '__init__.py':
                has_python_files = True
            zf.write(os.path.join(root, the_file), os.path.relpath(os.path.join(root, the_file), os.path.join(args.directory, '..')))
    zf.close()
    archive.seek(0)
    if args.norestart:
        should_restart = False
    elif args.force_restart or has_python_files:
        should_restart = True
    elif len(dependencies) > 0 or this_package_name:
        r = requests.get(apiurl + '/api/package', headers={'X-API-Key': apikey})
        if r.status_code != 200:
            sys.exit("/api/package returned " + str(r.status_code) + ": " + r.text)
        installed_packages = r.json()
        already_installed = False
        for package_info in installed_packages:
            package_info['alt_name'] = re.sub('^docassemble\.', 'docassemble-', package_info['name'])
            for dependency_name, dependency_info in dependencies.items():
                if dependency_name in (package_info['name'], package_info['alt_name']):
                    condition = True
                    if dependency_info['operator']:
                        if dependency_info['operator'] == '==':
                            condition = version.parse(package_info['version']) == version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '<=':
                            condition = version.parse(package_info['version']) <= version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '>=':
                            condition = version.parse(package_info['version']) >= version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '<':
                            condition = version.parse(package_info['version']) < version.parse(dependency_info['version'])
                        elif dependency_info['operator'] == '>':
                            condition = version.parse(package_info['version']) > version.parse(dependency_info['version'])
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
        project_list = requests.get(project_endpoint, headers={'X-API-Key': apikey})
        if project_list.status_code == 200:
            if not args.project in project_list:
                try:
                    create_project = requests.post(project_endpoint, data={'project': args.project}, headers={'X-API-Key': apikey})
                except:
                    sys.exit("create project POST returned " + project_list.text)
        else:
            sys.stdout.write("\n")
            sys.exit("playground list of projects GET returned " + str(project_list.status_code) + ": " + project_list.text)
        r = requests.post(apiurl + '/api/playground_install', data=data, files={'file': archive}, headers={'X-API-Key': apikey})
        if r.status_code == 400:
            try:
                error_message = r.json()
            except:
                error_message = ''
            if 'project' not in data or error_message != 'Invalid project.':
                sys.exit('playground_install POST returned ' + str(r.status_code) + ": " + r.text)
            r = requests.post(apiurl + '/api/playground/project', data={'project': data['project']}, headers={'X-API-Key': apikey})
            if r.status_code != 204:
                sys.exit("needed to create playground project but POST to api/playground/project returned " + str(r.status_code) + ": " + r.text)
            archive.seek(0)
            r = requests.post(apiurl + '/api/playground_install', data=data, files={'file': archive}, headers={'X-API-Key': apikey})
        if r.status_code == 200:
            try:
                info = r.json()
            except:
                sys.exit(r.text)
            task_id = info['task_id']
            success = wait_for_server(args.playground, task_id, apikey, apiurl)
        elif r.status_code == 204:
            success = True
        else:
            sys.stdout.write("\n")
            sys.exit("playground_install POST returned " + str(r.status_code) + ": " + r.text)
        if success:
            sys.stdout.write("\nInstalled.\n")
            sys.stdout.flush()
        else:
            sys.exit("\nInstall failed\n")
    else:
        r = requests.post(apiurl + '/api/package', data=data, files={'zip': archive}, headers={'X-API-Key': apikey})
        if r.status_code != 200:
            sys.exit("package POST returned " + str(r.status_code) + ": " + r.text)
        info = r.json()
        task_id = info['task_id']
        if wait_for_server(args.playground, task_id, apikey, apiurl):
            sys.stdout.write("\nInstalled.\n")
        if not should_restart:
            r = requests.post(apiurl + '/api/clear_cache', headers={'X-API-Key': apikey})
            if r.status_code != 204:
                sys.exit("clear_cache returned " + str(r.status_code) + ": " + r.text)
    sys.exit(0)


def dacreate():
    dotfile = os.path.join(os.path.expanduser('~'), '.docassemblecli')
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
        sys.exit("The package name you entered is invalid.")
    pkgname = re.sub(r'^docassemble[\-\.]', '', pkgname, flags=re.IGNORECASE)
    if args.output:
        packagedir = args.output
    else:
        packagedir = 'docassemble-' + pkgname
    if os.path.exists(packagedir):
        if not os.path.isdir(packagedir):
            sys.exit("Cannot create the directory " + packagedir + " because the path already exists.")
        dir_listing = list(os.listdir(packagedir))
        if 'setup.py' in dir_listing or 'setup.cfg' in dir_listing:
            sys.exit("The directory " + packagedir + " already has a package in it.")
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
    license = args.license
    if not license:
        license = input('License of package [MIT]: ').strip()
        if not license:
            license = "MIT"
    version = args.version
    if not version:
        version = input('Version of package [0.0.1]: ').strip()
        if not version:
            version = "0.0.1"
    initpy = """\
__import__('pkg_resources').declare_namespace(__name__)

"""
    if 'MIT' in license:
        licensetext = 'The MIT License (MIT)\n\nCopyright (c) ' + str(datetime.datetime.now().year) + ' ' + developer_name + """

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
        licensetext = license + "\n"
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
      license=""" + repr(license) + """,
      url=""" + repr(package_url) + """,
      packages=find_packages(),
      namespace_packages=['docassemble'],
      install_requires=[],
      zip_safe=False,
      package_data=find_package_data(where='docassemble/""" + pkgname + """/', package='docassemble.""" + pkgname + """'),
     )
"""
    maindir = os.path.join(packagedir, 'docassemble', pkgname)
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
    with open(os.path.join(packagedir, 'README.md'), 'w', encoding='utf-8') as the_file:
        the_file.write(readme)
    with open(os.path.join(packagedir, 'LICENSE'), 'w', encoding='utf-8') as the_file:
        the_file.write(licensetext)
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
    sys.exit(0)
