$env:FLASK_APP = "spades.py"
$env:FLASK_ENV = "development"
.\spades\Scripts\activate
python -m flask run --cert=cert.pem --key=key.pem