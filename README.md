# swe681-spades
Final project for SWE681 - Four player spades

Prerequirements
===
* OpenSSL
* Python 3.7 or later
* MySQL Server 5.7

Setup
===
From the project root directory, run the following command to generate certificates:

`openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365`

Copy the `default.cfg` config file to a secure location outside of the webserver.
Export the path to the shell variable `SPADES_APP_CONFIG` from your shell:
```shell script
EXPORT SPADES_APP_CONFIG=/etc/local/spades/local.cfg
```
NOTE: This assumes the path `/etc/local/spades/local.cfg`. If you place your local config file elsewhere,
use that path instead.

Log in to MySQL to an account with privileges to create databases and new users.
Create a new database `spades` and a new user `spades_app` with `INSERT`, `SELECT`, and `UPDATE` roles
by running the following commands at the MySQL interface:
```mysql
CREATE DATABASE spades;
CREATE USER 'spades_app'@'localhost' IDENTIFIED BY 'password';
GRANT INSERT, SELECT, UPDATE ON spades.* TO 'spades_app'@'localhost';
```
NOTES:
* DO NOT USE THE PASSWORD `password`! Pick a strong password and supply that to the command instead.
* Change `localhost` where necessary if you are running MySQL remotely.

[TODO: include steps for generating secret key for sessions]

Running the Game
===
To run with standalone Flask webserver:

`python -m flask run --cert=cert.pem --key=key.pem`

A Windows PowerShell script has been included for convenience. You may execute it instead:

'./starter.ps1'

Playing the Game
===
Visit `https://localhost:5000` in your browser.
