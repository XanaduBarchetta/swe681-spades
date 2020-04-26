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

[TODO: include db setup steps]

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
