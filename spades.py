from flask import Flask, request, render_template

app = Flask(__name__)
app.config['EXPLAIN_TEMPLATE_LOADING'] = True

@app.route('/')
def hello_world():
    return render_template('login.html')

@app.route('/', methods=['POST'])
def my_form_post():
    text = request.form['text']
    processed_text = text.upper()
    return processed_text