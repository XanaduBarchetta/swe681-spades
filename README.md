# swe681-spades
Final project for SWE681 - Four player spades

Prereqs: OpenSSL. Python 3.8.

From the project root directory, run the following command:

`openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365`

To run with standalone Flask webserver:

`python -m flask run --cert=cert.pem --key=key.pem`

Visit `https://localhost:5000` in your browser.
