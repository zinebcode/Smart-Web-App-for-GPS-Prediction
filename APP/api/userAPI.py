import uuid
import requests
from flask import Blueprint, request, jsonify, redirect, url_for, render_template, flash, session
from firebase_admin import firestore, db
from haversine import haversine, Unit
import pandas as pd
from datetime import datetime
from dateutil.parser import parse
from sklearn.preprocessing import MinMaxScaler
from keras.models import Sequential
from keras.layers import LSTM, Dense

userAPI = Blueprint('userAPI', __name__)
firestore_db = firestore.client()
realtime_db = db.reference('/capteurs/gps/realtime')
user_Ref = firestore_db.collection('account')


def clean_time_format(time_str):
    time_str = time_str.strip()
    if len(time_str) == 25 and time_str[10] != 'T':
        time_str = time_str[:10] + 'T' + time_str[10:]
    if len(time_str) == 24:
        time_str = time_str[:22] + '00:00'
    return time_str


def process_data(data):
    try:
        for key in data:
            data[key]['Time'] = clean_time_format(data[key]['Time'])
        data_list = []
        for key, value in data.items():
            data_list.append({
                'Longitude': value['Longitude'],
                'Latitude': value['Latitude'],
                'Altitude': value['Altitude'],
                'Time': value['Time'],
                'Actual_Speed': value['Actual_Speed']
            })
        for item in data_list:
            item['Time'] = datetime.strptime(item['Time'], '%Y-%m-%dT%H:%M:%S%z')
        sorted_data = sorted(data_list, key=lambda x: x['Time'], reverse=True)[:2]
        if len(sorted_data) < 2:
            return "Not enough data points to process."
        time1 = sorted_data[0]['Time']
        longitude1 = sorted_data[0]['Longitude']
        latitude1 = sorted_data[0]['Latitude']
        altitude1 = sorted_data[0]['Altitude']
        actual_speed1 = sorted_data[0]['Actual_Speed']
        time2 = sorted_data[1]['Time']
        longitude2 = sorted_data[1]['Longitude']
        latitude2 = sorted_data[1]['Latitude']
        altitude2 = sorted_data[1]['Altitude']
        actual_speed2 = sorted_data[1]['Actual_Speed']
        data_list = [
            [longitude1, latitude1, altitude1, time1, actual_speed1],
            [longitude2, latitude2, altitude2, time2, actual_speed2]
        ]
        columns = ['Longitude', 'Latitude', 'Altitude', 'Time', 'Actual_Speed']
        df = pd.DataFrame(data_list, columns=columns)

        df['Time_diff'] = df['Time'].diff().dt.total_seconds().abs()
        df['Time_diff'].fillna(0, inplace=True)
        df['Haversine_Distance'] = 0.0
        df['Calculated_Speed'] = 0.0
        if len(df) > 1:
            loc1 = (df.at[0, 'Latitude'], df.at[0, 'Longitude'])
            loc2 = (df.at[1, 'Latitude'], df.at[1, 'Longitude'])
            df.at[1, 'Haversine_Distance'] = haversine(loc1, loc2) * 1000
            if df.at[1, 'Time_diff'] != 0:
                df.at[1, 'Calculated_Speed'] = df.at[1, 'Haversine_Distance'] / df.at[1, 'Time_diff']
        return df
    except Exception as e:
        return f"An Error Occurred: {e}"


def additional_processing(longitude, latitude, time_diff, haversine_distance, calculated_speed):
    try:
        data_list = [
            [longitude, latitude, time_diff, haversine_distance, calculated_speed]
        ]
        columns = ['Longitude', 'Latitude', 'Time_diff', 'Haversine_Distance', 'Calculated_Speed']
        df = pd.DataFrame(data_list, columns=columns)

        sc = MinMaxScaler(feature_range=(-1, 1))
        x_data = df[['Longitude', 'Latitude', 'Time_diff', 'Haversine_Distance', 'Calculated_Speed']].values
        new_x_data = sc.fit_transform(x_data)
        # Remodelage des données pour correspondre au format attendu (batch_size, time_steps, features)
        new_x_data = new_x_data.reshape(1, 5, 1)

        return new_x_data
    except Exception as e:
        return f"An Error Occurred: {e}"


def get_address_from_coords(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&addressdetails=1"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        data = response.json()
        if 'display_name' in data:
            return data['display_name']
        else:
            return 'Address not found'
    except requests.exceptions.RequestException as e:
        print(f"Error fetching address: {e}")
        return 'Error fetching address'

#login
@userAPI.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form['email']
            password = request.form['password']

            user_query = user_Ref.where('email', '==', email).stream()
            user = next(user_query, None)

            if user:
                user_data = user.to_dict()
                if user_data['password'] == password:
                    session['email'] = email
                    return redirect(url_for('userAPI.index1'))
                else:
                    flash('Mot de passe incorrect.', 'danger')
            else:
                flash('Utilisateur non trouvé.', 'danger')
        except Exception as e:
            flash(f"Une erreur s'est produite: {e}", 'danger')
    return render_template('login.html')


@userAPI.route('/index')
def index():
    return render_template('index.html')

@userAPI.route('/page1')
def index1():
    try:
        # Récupérer les données en temps réel
        data = realtime_db.get()

        # Assurez-vous que ' Actual_Speed' est correctement formaté
        for timestamp, values in data.items():
            if ' Actual_Speed' in values:
                values['Actual_Speed'] = values.pop(' Actual_Speed')

        # Obtenir la date et l'heure actuelles
        current_date = datetime.now().strftime('%Y/%m/%d')
        current_time = datetime.now().strftime('%H:%M:%S')

        # Récupérer les dernières coordonnées
        latest_data = max(data.values(), key=lambda x: x['Time'])
        lat = latest_data.get('Latitude')
        lon = latest_data.get('Longitude')

        # Vérifier si les coordonnées sont valides
        if lat is not None and lon is not None:
            # Récupérer l'adresse à partir des coordonnées
            address = get_address_from_coords(lat, lon)
        else:
            address = 'Latitude and/or Longitude not found'

        # Rendre le modèle avec l'adresse
        return render_template('page1.html', address=address,lat=lat, 
                               lon=lon, current_date=current_date,
                               current_time=current_time)

    except Exception as e:
        return f"An Error Occurred: {e}"
 

# Chargement du modèle
def load_model():
    model = Sequential()
    model.add(LSTM(50, input_shape=(5, 1), return_sequences=True))
    model.add(Dense(2))
    model.load_weights('model/model2.h5', by_name=True)
    return model


@userAPI.route('/page2')
def index3():
     # Récupérer les données en temps réel
        data = realtime_db.get()

        # Assurez-vous que ' Actual_Speed' est correctement formaté
        for timestamp, values in data.items():
            if ' Actual_Speed' in values:
                values['Actual_Speed'] = values.pop(' Actual_Speed')

        # Récupérer les dernières coordonnées
        latest_data = max(data.values(), key=lambda x: x['Time'])
        
        lat = latest_data.get('Latitude')
        lon = latest_data.get('Longitude')

        # Vérifier si les coordonnées sont valides
        if lat is not None and lon is not None:
            # Récupérer l'adresse à partir des coordonnées
            address = get_address_from_coords(lat, lon)
        else:
            address = 'Latitude and/or Longitude not found'

        processed_df = process_data(data)

        if isinstance(processed_df, str):  
            return processed_df

        new_x_data = additional_processing(
            longitude=latest_data.get('Longitude'),
            latitude=latest_data.get('Latitude'),
            time_diff=processed_df['Time_diff'][1],
            haversine_distance=processed_df['Haversine_Distance'][1],
            calculated_speed=processed_df['Calculated_Speed'][1]
        )
        # Prédiction avec le modèle
        model = load_model()
        prediction = model.predict(new_x_data)
        
        # Récupérer les coordonnées prédites
        predicted_coords = prediction[0]
        lat=predicted_coords[0]
        lon=predicted_coords[1]

        address = get_address_from_cords(lat, lon)


        # Rendre le modèle avec l'adresse
        return render_template('page2.html', address=address['address'],lat=address['latitude'], 
                               lon=address['longitude'])

#la page du tableau
@userAPI.route('/data')
def index2():
    try:
        data = realtime_db.get()

        for timestamp, values in data.items():
            if ' Actual_Speed' in values:
                values['Actual_Speed'] = values.pop(' Actual_Speed')

        latest_data = max(data.values(), key=lambda x: x['Time'])

        lat = latest_data.get('Latitude')
        lon = latest_data.get('Longitude')

        if lat is not None and lon is not None:
            address = get_address_from_coords(lat, lon)
        else:
            address = 'Latitude and/or Longitude not found'

        processed_df = process_data(data)
        if isinstance(processed_df, str):  
            return processed_df

        # Extraire la deuxième ligne
        second_row = processed_df.iloc[1].to_dict() if len(processed_df) > 1 else None

        return render_template('data.html', second_row=second_row)
    except Exception as e:
        return f"An Error Occurred: {e}"
















#Fin code 
#non inclus 

@userAPI.route('/add', methods=['POST'])
def create():
    try:
        id = uuid.uuid4()
        user_Ref.document(str(id)).set(request.json)
        return jsonify({"success": True}), 200
    except Exception as e:
        return f"An Error Occurred: {e}"

#non inclus 
@userAPI.route('/success')
def success():
    try:
        data = realtime_db.get()

        for timestamp, values in data.items():
            if ' Actual_Speed' in values:
                values['Actual_Speed'] = values.pop(' Actual_Speed')

        latest_data = max(data.values(), key=lambda x: x['Time'])

        lat = latest_data.get('Latitude')
        lon = latest_data.get('Longitude')

        if lat is not None and lon is not None:
            address = get_address_from_coords(lat, lon)
        else:
            address = 'Latitude and/or Longitude not found'

        processed_df = process_data(data)

        if isinstance(processed_df, str):  
            return processed_df

        new_x_data = additional_processing(
            longitude=latest_data.get('Longitude'),
            latitude=latest_data.get('Latitude'),
            time_diff=processed_df['Time_diff'][1],
            haversine_distance=processed_df['Haversine_Distance'][1],
            calculated_speed=processed_df['Calculated_Speed'][1]
        )

        # Prédiction avec le modèle
        model = load_model()
        prediction = model.predict(new_x_data)
        
        # Récupérer les coordonnées prédites
        predicted_coords = prediction[0]

        avg_speed = processed_df['Actual_Speed'].mean()
        total_distance = processed_df['Haversine_Distance'].sum() / 1000 

        return render_template('success.html', 
                               data=processed_df.to_dict(orient='index'), 
                               address=address, 
                               lat=lat, 
                               lon=lon, 
                               avg_speed=avg_speed, 
                               total_distance=total_distance,
                               predicted_lat=predicted_coords[0],
                               predicted_lon=predicted_coords[1],
                               new_x_data=new_x_data)
    except Exception as e:
        return f"An Error Occurred: {e}"



#non inclus 
@userAPI.route("/list")
def read():
    try:
        all_users = [doc.to_dict() for doc in user_Ref.stream()]
        return jsonify(all_users), 200
    except Exception as e:
        return f"An Error Occurred: {e}"
#non inclus 

def get_address_from_cords(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={36.2419358}&lon={6.5615020}&addressdetails=1"
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        data = response.json()
        if 'display_name' in data:
            return {
                'address': data['display_name'],
                'latitude': 36.2419358,
                'longitude': 6.5615020
            }
        else:
            return {
                'address': 'Address not found',
                'latitude': 36.2419358,
                'longitude': 6.5615020
            }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching address: {e}")
        return 'Error fetching address'