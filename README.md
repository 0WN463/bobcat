# bobcat

A CLI tool to interface with [Kattis](https://open.kattis.com/), the online judge.

https://user-images.githubusercontent.com/35750423/184792107-77e06e09-4865-4be1-bd2a-f864afad96e8.mp4

## Features

* Browse questions 
* Submit solution
* Run and test solution against samples
* Multiple options to configure

All in the command line, without having to nagivate Kattis' website.

## Installation

### From AUR

If you are using Arch Linux, this script is available on the [AUR](https://aur.archlinux.org/packages/bobcat-git).
Use the AUR helper of your choice, _eg_ `yay`.

```
yay -S bobcat-git
```

### From source

``` sh
git clone https://github.com/0WN463/bobcat
cd bobcat
pip install .
```

## Configuration

### Config file

Config will be retrieved in order from `$XDG_CONFIG_HOME/bobcat/config.ini`, `$HOME/.bobcat.ini` and `<SCRIPT_PATH>/config.ini` (default config).

An example of the config file can be referenced from the [default config](https://github.com/0WN463/bobcat/blob/main/bobcat/config.ini).

### Login credentials

To avoid having to continually login, `bobcat` will try to reference `.secret.ini` under your `CONFIG_DIR` (`XDG_CONFIG_HOME` if it is set, otherwise `HOME`).
It should have the following structure.

``` ini
[credentials]
user = ...
password = ....
```

Note that this storage is insecure, so use at your own risk.

### Skipped questions

To keep record of questions that were previously skipped, the ID of skipped questions are stored in plain-text under `$XDG_STATE_HOME/bobcat/skipped` (`$HOME/.local/state/bobcat/skipped` if `XDG_STATE_HOME` is not defined)

