# docassemblecli

`docassemblecli` provides command-line utilities for interacting with
[docassemble] servers.  This package is meant to be installed on your
local machine, not on a [docassemble] server.

## Prerequisites

The `dainstall` program requires that you have Python installed on
your computer. The `dawatchinstall` program requires `bash` and
`fswatch`. These prerequisites are easy to find on Linux machines, but
are harder to install on Windows and Mac systems. If you run Windows,
see the last section of this README for instructions on getting a
command line in Windows Subsystem for Linux.

## Installation

To install `docassemblecli` from PyPI, run:

    pip install docassemblecli

## Usage

Currently, `docassemblecli` provides one command-line utility called
`dainstall`, which installs a Python package on a remote server using
files on your local computer.

For example, suppose that you wrote a docassemble extension package
called `docassemble.foobar` using the **docassemble** Playground.  In
the Playground, you can download the package as a ZIP file called
`docassemble-foobar.zip`.  You can then unpack this ZIP file and see a
folder called `docassemble-foobar`.  Inside of this folder there is a
folder called `docassemble` and a `setup.py` file.

From the command line, use `cd` to navigate to the folder that
contains the `docassemble-foobar` folder.  Then run:

    dainstall docassemble-foobar

On Windows, you will need to write `python -m
docassemblecli.dainstall` in place of `dainstall`, so your command
will look like this:

    python -m docassemblecli.dainstall docassemble-foobar

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

    $ dainstall [-h] [--apiurl APIURL] [--apikey APIKEY] [--norestart]
                     [--server SERVER] [--playground] [--project PROJECT] [--add]
                     [--noconfig]
                     [directory]

    positional arguments:
      directory

    optional arguments:
      -h, --help         show this help message and exit
      --apiurl APIURL    base url of your docassemble server, e.g.
                         https://da.example.com
      --apikey APIKEY    docassemble API key
      --norestart        do not restart the docassemble server after installing
                         package (only applicable in single-server environments)
      --server SERVER    use a particular server from the .docassemblecli config
                         file
      --playground       install into your Playground instead of into the server
      --project PROJECT  install into a specific project in the Playground
      --add              add another server to the .docassemblecli config file
      --noconfig         do not use the .docassemblecli config file

For example, you might want to pass the URL and API key in the command
itself:

    dainstall --apiurl https://dev.example.com --apikey H3PWMKJOIVAXL4PWUJH3HG7EKPFU5GYT docassemble-foobar

If you have more than one server, you can run:

    dainstall --add

to add an additional server configuration to store in your
`.docassemblecli` config file.  Then you can select the server using
`--server`:

   dainstall --server dev.example.com docassemble-foobar

If you do not specify a `--server`, the first server indicated in your
`.docassemblecli` file will be used.

The `--norestart` option can be used when your **docassemble**
installation only uses one server (which is typical) and you are not
modifying .py files.  In this case, it is not necessary for the Python
web application to restart after the package has been installed.  This
will cause `dainstall` to return a few seconds faster than otherwise.

By default, `dainstall` installs a package on the server.  If you want
to install a package into your Playground, you can use the
`--playground` option.

   dainstall --playground docassemble.foobar

If you want to install into a particular project in your Playground,
indicate the project with `--project`.

   dainstall --playground --project testing docassemble-foobar

Installing into the Playground with `--playground` is faster than
installing an actual Python package because it does not need to run
`pip`.

If your development installation uses more than one server, it is safe
to run `dainstall --playground` with `--norestart` if you are only
changing YAML files, because Playground YAML files are stored in cloud
storage and will thus be available immediately to all servers.

## How it works

The `dainstall` command is just a simple Python script that creates a
ZIP file and uploads it through the **docassemble** API.  Feel free to
copy the code and write your own scripts to save yourself time.

## Automatically calling `dainstall`

You can use the `bash` script `dawatchinstall` to call `dainstall`
automatically every time a file in your package directory is changed.

For example, if you run:

    dawatchinstall --playground --project testing docassemble-foobar

This will monitor the `docassemble-foobar` directory, and if any file
changes, it will run:

    dainstall --playground --project testing --norestart docassemble-foobar

If a `.py` file is changed, however, it will run

    dainstall --playground --project testing docassemble-foobar

With `dawatchinstall --playground` constantly running, then after you
save a YAML file on your local machine, it will be available for
testing on your server very quickly.

To exit `dawatchinstall`, type Ctrl-c.

To use this, both `dawatchinstall` and `dainstall` need to be in your
path; if it is not, you will need to edit the `dawatchinstall` script
so that it can successfully call the `dainstall` script.

The `dawatchinstall` script depends on the `fswatch` command.  If this
command is not available on your system, you may need to install the
`fswatch` package.

## Running on Windows

If you are running Windows, a relatively convenient way to install
these command-line utilities is to use Windows Subsystem for Linux.

In the Microsoft Store, search for "Ubuntu" and install it. This may
require restarting your Windows machine. (Other Linux distributions
will work just as well, so feel free to use a different distribution
if you know what you are doing.)

Then run the Ubuntu app and answer the prompts to complete the
installation.

From the Ubuntu command line, do:

    sudo apt -y update
    sudo apt -y install python3-pip fswatch
    sudo pip install docassemblecli
    dainstall --add

The last command, `dainstall --add`, will ask for your docassemble
site URL and your API key. The API key that you supply needs to belong
to a user with `developer` or `admin` privileges.

Use `cd` to switch to the directory above where your docassemble
package is located. (Your Windows hard drive is located at `/mnt/c`
inside of Ubuntu.)

For example, assume you have a folder `docassemble-mypackage` on your
Desktop, and your username on your machine is `jsmith`. You would do:

    cd /mnt/c/Users/jsmith/Desktop/

From there, you can run commands like:

    dainstall docassemble-mypackage

or

    dawatchinstall --playground --project mypack docassemble-mypackage

[API key]: https://docassemble.org/docs/api.html#manage_api
[docassemble]: https://docassemble.org
