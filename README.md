# docassemblecli

`docassemblecli` provides command-line utilities for interacting with
[docassemble] servers. This package is meant to be installed on your
local machine, not on a [docassemble] server.

## Prerequisites

The utility programs in `docassemblecli` require that you have Python
installed on your computer. If you are using MacOS or Linux, you
probably have Python installed already.

### Installing Python on Windows

If you are using Windows and you have not installed Python before, it
is recommended that you download Python from the [python.org download
page] rather than using the Microsoft Store. When you run the
installer, there will be two checkbox options ("Use admin privileges
when installing py.exe" and "Add python.exe to PATH"), and you should
check both of them. Later on in the installation, you may be prompted
to extend the maximum length of the `PATH` variable beyond 250
characters. You should click the button to make this
change. Installing Python this way will make it much easier to run the
utilities because you will not need to manually adjust your `PATH`.

Note that when you have installed Python on Windows, an application
called "Python" will be available from the start menu. This
application runs the [Python Interpreter]. The Python Interpreter is a
very useful tool, but it is not the tool for installing
`docassemblecli` or running the command line utilities `dainstall`,
`dauninstall`, `dacreate`, and `dadownload`. To run these commands,
you need to use the Windows command line application, called `cmd`.

### Using a command line

In order to install `docassemblecli` and use the utilities, you will
need to run an application that gives you a command line. On MacOS,
you can use the [Terminal application], which comes with the operating
system. On Windows, you can go to the start menu and search for "cmd,"
which is the name of the [Windows command line application].

## Installation

To install `docassemblecli` from PyPI, run:

    pip3 install docassemblecli

If you get an error, you may not have installed Python, or may not
have installed it correctly. If you only have Python 2.7 installed,
install the latest version of Python instead (e.g., Python 3.12 or
greater.) If you know you have installed Python, but `pip3` is not a
recognized command, you might need to manually adjust your `PATH`.

To upgrade `docassemblecli` after you have already installed it, do:

    pip3 install --upgrade docassemblecli

## Usage

### dacreate

`docassemblecli` provides a command-line utility called `dacreate`,
which creates an empty **docassemble** add-on package.

To create a package called `docassemble-foobar`, run:

    dacreate foobar

You will be asked some questions about the package and the
developer. This information is necessary because it goes into the
`setup.py`, `README.md`, and `LICENSE` files of the package. If you do
not yet know what answers to give, just press enter, and you can edit
these files later.

When the command exits, you will find a directory in the current
directory called `docassemble-foobar` containing a shell of a
**docassemble** add-on package.

You can run `dacreate --help` to get more information about how
`dacreate` works:

    usage: dacreate [-h] [--developer-name DEVELOPER_NAME]
                    [--developer-email DEVELOPER_EMAIL]
                    [--description DESCRIPTION] [--url URL] [--license LICENSE]
                    [--version VERSION] [--output OUTPUT]
                    [package]

    positional arguments:
      package               name of the package you want to create

    options:
      -h, --help            show this help message and exit
      --developer-name DEVELOPER_NAME
                            name of the developer of the package
      --developer-email DEVELOPER_EMAIL
                            email of the developer of the package
      --description DESCRIPTION
                            description of package
      --url URL             URL of package
      --license LICENSE     license of package
      --version VERSION     version number of package
      --output OUTPUT       output directory in which to create the package

### dainstall

`docassemblecli` provides a command-line utility called `dainstall`,
which installs a Python package on a remote server using files on your
local computer.

For example, suppose that you wrote a docassemble extension package
called `docassemble.foobar` using the **docassemble** Playground. In
the Playground, you can download the package as a ZIP file called
`docassemble-foobar.zip`. You can then unpack this ZIP file and you
will see a folder called `docassemble-foobar`. Inside of this folder
there is a folder called `docassemble` and a `setup.py` file. Your
interview YAML files will be in the folder
`docassemble/foobar/data/questions`. Your templates will be in the
folder `docassemble/foobar/data/templates`. Your modules will be in
the folder `docassemble/foobar`. Now you can use your favorite text
editor to edit your `.yml` and `.py` files, and you can use
`dainstall` to install the package on your server so that you can test
your changes.

From the command line, use `cd` to navigate to the folder that
contains the `docassemble-foobar` folder. Then run:

    dainstall docassemble-foobar

The first time you run this command, it will ask you for the URL of
your **docassemble** server and the [API key] of a user with `admin` or
`developer` privileges.

It will look something like this:

    $ dainstall docassemble-foobar
    Base URL of your docassemble server (e.g., https://da.example.com): https://dev.example.com
    API key of admin user on http://localhost: H3PWMKJOIVAXL4PWUJH3HG7EKPFU5GYT
    Saved base URL and API key to .docassemblecli
    Waiting for package to install.............................
    Installed.

The next time you run `dainstall`, it will not ask you for the URL and
API key.

You can run `dainstall --help` to get more information about how
`dainstall` works:

    usage: dainstall [-h] [--apiurl APIURL] [--apikey APIKEY] [--norestart]
                     [--watch] [--force-restart] [--server SERVER] [--playground]
                     [--project PROJECT] [--add] [--noconfig] [--debug]
                     [directory]

    positional arguments:
      directory

    options:
      -h, --help         show this help message and exit
      --apiurl APIURL    base url of your docassemble server, e.g.
                         https://da.example.com
      --apikey APIKEY    docassemble API key
      --norestart        do not restart the docassemble server after installing
                         package (only applicable in single-server environments)
      --watch            watch the directory for changes and install changes when
                         there is a change
      --force-restart    unconditionally restart the docassemble server after
                         installing package
      --server SERVER    use a particular server from the .docassemblecli config
                         file
      --playground       install into your Playground instead of into the server
      --project PROJECT  install into a specific project in the Playground
      --add              add another server to the .docassemblecli config file
      --noconfig         do not use the .docassemblecli config file
      --debug            use verbose logging

For example, you might want to pass the URL and API key in the command
itself:

    dainstall --apiurl https://dev.example.com --apikey H3PWMKJOIVAXL4PWUJH3HG7EKPFU5GYT docassemble-foobar

If you have more than one server, you can run:

    dainstall --add

to add an additional server configuration to store in your
`.docassemblecli` config file. Then you can select the server using
`--server`:

    dainstall --server dev.example.com docassemble-foobar

If you do not specify a `--server`, the first server indicated in your
`.docassemblecli` file will be used.

The `--norestart` option can be used when your **docassemble**
installation only uses one server (which is typical) and you are not
modifying .py files. In this case, it is not necessary for the Python
web application to restart after the package has been installed. This
will cause `dainstall` to return a few seconds faster than otherwise.

The `--force-restart` option should be used when you want to make sure
that **docassemble** restarts the Python web application after the
package is installed. By default, `dainstall` will avoid restarting
the server if the package has no module files and all of its
dependencies (if any) are installed.

By default, `dainstall` installs a package on the server. If you want
to install a package into your Playground, you can use the
`--playground` option.

    dainstall --playground docassemble.foobar

If you want to install into a particular project in your Playground,
indicate the project with `--project`.

    dainstall --playground --project testing docassemble-foobar

Installing into the Playground with `--playground` is faster than
installing an actual Python package because it does not need to run
`pip`.

If you are using a multi-server configuration, it is safe to run
`dainstall --playground` with `--norestart` if you are only changing
YAML files, because Playground YAML files are stored in cloud storage
and will thus be available immediately to all servers.

You can run `dainstall` with the `--watch` option if you want your
package to be automatically updated on the server every time a file in
your package directory is changed.

For example, suppose you run:

    dainstall --watch --playground --project testing docassemble-foobar

This will monitor the `docassemble-foobar` directory, and if any file
within the directory is modified, or a new file is created, the
package will be reinstalled into the `testing` project of the
Playground belonging to the owner of the API key.

To exit, type Ctrl-c.

The `--watch` feature tries to be as efficient as possible. If you
modify a file in the `data` folder, it will not restart the server
afterward. However, it will restart the server if you modify a `.py`
file, because otherwise you would not be able to see the effect of the
change. If you are using `--playground`, the `dainstall --watch`
feature will only upload the specific file or files that you modified,
rather than uploading the whole package.

Thus, for the fastest development experience, use `--watch` and
`--playground`.

If you encounter problems, try running dainstall with the `--debug`
option.

### dauninstall

The `dauninstall` utility uninstalls a package from a **docassemble**
server.

    usage: dauninstall [-h] [--apiurl APIURL] [--apikey APIKEY] [--norestart]
                       [--server SERVER] [--noconfig] [--debug]
                       package

    positional arguments:
      package

    options:
      -h, --help       show this help message and exit
      --apiurl APIURL  base url of your docassemble server, e.g.
                       https://da.example.com
      --apikey APIKEY  docassemble API key
      --norestart      do not restart the docassemble server after installing
                       package (only applicable in single-server environments)
      --server SERVER  use a particular server from the .docassemblecli config
                       file
      --noconfig       do not use the .docassemblecli config file
      --debug          use verbose logging

### dadownload

The `dadownload` utility downloads a package from a **docassemble**
server and saves it to the current working directory. It connects to
a **docassemble** server in the same way that `dainstall` does.

    usage: dadownload [-h] [--overwrite] [--apiurl APIURL] [--apikey APIKEY]
                      [--server SERVER] [--playground] [--project PROJECT] [--add]
                      [--noconfig]
                      [package]

    positional arguments:
      package

    options:
      -h, --help         show this help message and exit
      --overwrite        overwrite existing files
      --apiurl APIURL    base url of your docassemble server, e.g.
                         https://da.example.com
      --apikey APIKEY    docassemble API key
      --server SERVER    use a particular server from the .docassemblecli config
                         file
      --playground       download from the Playground
      --project PROJECT  download from a specific project in the Playground
      --add              add another server to the .docassemblecli config file
      --noconfig         do not use the .docassemblecli config file

For example, if you run `dadownload docassemble.foo` (or `dadownload
foo`, which will do the same thing), a directory `docassemble-foo`
will be created, containing the `docassemble.foo` package that is
installed on the **docassemble** server.

If you use `--playground`, then the files specified in a package in
the Packages folder of the Playground will be collected and downloaded
to the current working directory.

Without `--playground`, the package that is installed on the server
will be downloaded to the current working directory. This only works
if the package was installed by uploading a ZIP file. (Note that the
`dainstall` command installs packages by uploading a ZIP file.) If the
package you want to download is on GitHub, use `git clone` to obtain
it. If the package is only on PyPI, use `pip download` to download the
code.

By default, `dadownload` will not overwrite any existing files. You
can override this by specifying `--overwrite`.

## Text editors that create hidden and temporary files

Text editors often create hidden files and hidden directories in your
project folder for their own purposes, such as backup files and files
that facilitate [linting]. This can be problematic when you are using
`git`, because you do not want these temporary files to appear on
GitHub. These files may cause `dainstall --watch` to think that a
file in your project has been modified, when it actually has not.

The `dainstall` command tries to avoid this. If you have `git`
installed, `dainstall` will call `git ls-files` to see what your
`.gitignore` file is screening out, and then tries to avoid these
files. It also uses regular expressions to avoid certain files and
directories.

If your development environment triggers `dainstall --watch` too much,
submit a GitHub issue in the `jhpyle/docassemblecli` repository
explaining the situation. It may be possible to tweak the code to
avoid the unnecessary triggering.

[API key]: https://docassemble.org/docs/api.html#manage_api
[docassemble]: https://docassemble.org
[python.org download page]: https://www.python.org/downloads/
[Python Interpreter]: https://docs.python.org/3/tutorial/interpreter.html
[Terminal application]: https://support.apple.com/guide/terminal/welcome/mac
[Windows command line application]: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/windows-commands
[linting]: https://en.wikipedia.org/wiki/Lint_%28software%29
[VS Code]: https://code.visualstudio.com/
