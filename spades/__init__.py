from flask import Flask
app = Flask(__name__)

# config
app.config.from_envvar('SPADES_APP_CONFIG')

from spades import dbobjects, spades
