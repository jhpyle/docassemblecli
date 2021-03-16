# docassemblecli

`docassemblecli` provides command-line utilities for interacting with
[docassemble] servers.  This package is meant to be installed on your
local machine, not on a [docassemble] server.

## Prerequisites

You need to have Python installed on your computer.

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

   dainstall --server dev.example.com docassemble.foobar

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

   dainstall --playground --project testing docassemble.foobar

## How it works

The `dainstall` command is just a simple Python script that creates a
ZIP file and uploads it through the **docassemble** API.  Feel free to
copy the code and write your own scripts to save yourself time.

[API key]: https://docassemble.org/docs/api.html#manage_api
[docassemble]: https://docassemble.org
