from flask import Flask
from firebase_admin import credentials, initialize_app

# Initialiser Firebase avec les informations d'identification de service
cred = credentials.Certificate("APP/api/key.json")
default_app = initialize_app(cred, {
    'databaseURL': 'https://flutterapp-7d6c3-default-rtdb.europe-west1.firebasedatabase.app/'
})

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = '12345rtfescdvf'

    from .userAPI import userAPI
    app.register_blueprint(userAPI, url_prefix='/user')
    return app








