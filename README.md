# swe681-spades
Final project for SWE681 - Four player spades

Prereqs: OpenSSL. Python 3.8.

From this directory, follow these instructions
Run: `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365`

Then:
`python ./server.py`

Then go to `https://localhost:4443/`