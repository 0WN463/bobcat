# bobcat

A CLI tool to interface with [Kattis](https://open.kattis.com/), the online judge.

## Features

* Browse questions 
* Submit solution
* Run and test solution against samples
* Multiple options to configure

All in the command line, without having to traverse around Kattis' website.

## Installation

### From source

``` bash
git clone https://github.com/0WN463/bobcat
cd bobcat
pip install -r requirements.txt
```

Then add `bobcat.py` to your `PATH`.

## Configuration

### Config file

Config will be retrieved in order from `$XDG_CONFIG_HOME/bobcat/config.ini`, `$HOME/.bobcat.ini` and `$BINARY_PATH/config.ini` (default config).

An example of the config file can be referenced from the [default config](https://github.com/0WN463/bobcat/blob/main/config.ini).

### Login credentials

To avoid having to continually login, `bobcat` will try to reference `.secret.init` under your `CONFIG_DIR` (`XDG_CONFIG_HOME` if it is set, otherwise `HOME`).
It should have the following structure.

``` ini
[credentials]
user = ...
password = ....
```

Note that this storage is insecure, so use at your own risk.

### Skipped questions

To keep record of questions that were previously skipped, the ID of skipped questions are stored in plain-text under `$XDG_STATE_HOME/bobcat/skipped` (`$HOME/.local/state/bobcat/skipped` if `XDG_STATE_HOME` is not defined)

