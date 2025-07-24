#include <WiFi.h>
#include <FirebaseESP32.h>
#include <TinyGPS++.h>

// Définition des broches UART pour le GPS
#define GPS_RX_PIN 22
#define GPS_TX_PIN 23

const char* ssid = "P 30";
const char* password = "Zeyneb123";

#define FIREBASE_HOST "https://flutterapp-7d6c3-default-rtdb.europe-west1.firebasedatabase.app"
#define FIREBASE_API_KEY "AIzaSyCzANq7wAxq_o5NhK6d7mNSt5CMbguIndo"
#define FIREBASE_USER_EMAIL "zey@gmail.com"
#define FIREBASE_USER_PASSWORD "Zeyneb@123"

// Création d'une instance de la classe Firebase
FirebaseData firebaseData;
FirebaseAuth firebaseAuth;
FirebaseConfig firebaseConfig;

// Création d'une instance de la classe TinyGPS++
TinyGPSPlus gps;

void setup() {
  // Initialisation de la communication série avec le moniteur série
  Serial.begin(115200);

  // Initialisation de la communication série avec le GPS
  Serial2.begin(9600, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  // Connexion au WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connexion au WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("Connecté au WiFi");

  // Configuration de Firebase
  firebaseConfig.host = FIREBASE_HOST;
  firebaseConfig.api_key = FIREBASE_API_KEY;
  firebaseAuth.user.email = FIREBASE_USER_EMAIL;
  firebaseAuth.user.password = FIREBASE_USER_PASSWORD;

  Firebase.begin(&firebaseConfig, &firebaseAuth);
  Firebase.reconnectWiFi(true);

  if (Firebase.signUp(&firebaseConfig, &firebaseAuth, FIREBASE_USER_EMAIL, FIREBASE_USER_PASSWORD)) {
    Serial.println("Connexion Firebase réussie");
  } else {
    Serial.printf("Erreur de connexion Firebase: %s\n", firebaseData.errorReason().c_str());
  }
}

void loop() {
  static String gpsData = ""; // Stockage des données GPS
  // Nous vérifions si des données sont disponibles sur le port série du GPS
  while (Serial2.available()) {
    // Lecture des données du GPS
    char c = Serial2.read();
    gpsData += c;
    // Nous vérifions si une trame complète est reçue
    if (c == '\n') {
      // Vérification de trame si elle commence par "$GPGGA"
      if (gpsData.startsWith("$GPGGA")) {
        // Affichage de trame GPGGA sur le moniteur série
        Serial.print(gpsData);
        // Parse la trame GPGGA
        if (gpsData.indexOf(",") > 0) {
          char gpsCharArray[gpsData.length() + 1];
          gpsData.toCharArray(gpsCharArray, gpsData.length() + 1);
          parseGPGGA(gpsCharArray);
        }
      }
      // Vérification si la trame commence par "$GPVTG"
      if (gpsData.startsWith("$GPVTG")) {
        // Affiche la trame GPVTG sur le moniteur série
        Serial.print(gpsData);
        // Parse la trame GPVTG
        if (gpsData.indexOf(",") > 0) {
          char gpsCharArray[gpsData.length() + 1];
          gpsData.toCharArray(gpsCharArray, gpsData.length() + 1);
          parseGPVTG(gpsCharArray);
        }
      }
      // Réinitialise gpsData pour la prochaine trame
      gpsData = "";
    }
  }
}

void parseGPGGA(char* gpsData) {
  char* token = strtok(gpsData, ",");
  int index = 0;
  float time = 0.0, latitude = 0.0, longitude = 0.0, altitude = 0.0;
  int fixQuality = 0;
  
  while (token != NULL) {
    switch (index) {
      case 1:
        time = atof(token);
        break;
      case 2:
        latitude = convertToDegrees(atof(token));
        break;
      case 3:
        if (strcmp(token, "S") == 0) latitude = -latitude;
        break;
      case 4:
        longitude = convertToDegrees(atof(token));
        break;
      case 5:
        if (strcmp(token, "W") == 0) longitude = -longitude;
        break;
      case 6:
        fixQuality = atoi(token);  // Fix quality
        break;
      case 9:
        altitude = atof(token);
        break;
    }
    token = strtok(NULL, ",");
    index++;
  }

  // Seules les données valides sont envoyées
  if (fixQuality > 0 && latitude != 0.0 && longitude != 0.0 && altitude != 0.0 && time != 0.0) {
    sendToFirebase(latitude, longitude, altitude, time, 0.0);
  }
}

void parseGPVTG(char* gpsData) {
  char* token = strtok(gpsData, ",");
  int index = 0;
  float speed = 0.0;
  
  while (token != NULL) {
    switch (index) {
      case 7:
        speed = atof(token);
        break;
    }
    token = strtok(NULL, ",");
    index++;
  }

  if (speed != 0.0) {
    // Envoie la vitesse à Firebase avec des valeurs factices pour latitude, longitude, altitude et temps
    sendToFirebase(0.0, 0.0, 0.0, 0.0, speed);
  }
}

void sendToFirebase(float latitude, float longitude, float altitude, float time, float speed) {
  // Obtenir le timestamp actuel en secondes
  String timestamp = String(millis() / 1000);

  // Conversion du temps GPS en format ISO 8601
  String isoTime = convertGPSTimeToISO(time);

  // Créer les données JSON
  FirebaseJson json;
  if (latitude != 0.0) json.set("Latitude", latitude);
  if (longitude != 0.0) json.set("Longitude", longitude);
  if (altitude != 0.0) json.set("Altitude", altitude);
  if (time != 0.0) json.set("Time", isoTime);
  if (speed != 0.0) json.set("Actual_Speed", speed);
  
  // Créer le chemin
  String path = "/capteurs/gps/realtime/" + timestamp;

  // Envoyer les données à Firebase
  if (Firebase.setJSON(firebaseData, path.c_str(), json)) {
    Serial.println("Données envoyées à Firebase avec succès");
  } else {
    Serial.printf("Erreur lors de l'envoi des données à Firebase: %s\n", firebaseData.errorReason().c_str());
  }
}

float convertToDegrees(float rawDegrees) {
  int degrees = int(rawDegrees / 100);
  float minutes = rawDegrees - (degrees * 100);
  return degrees + minutes / 60.0;
}

String convertGPSTimeToISO(float time) {
  int hours = int(time / 10000);
  int minutes = int((time - hours * 10000) / 100);
  int seconds = int(time - hours * 10000 - minutes * 100);
  char isoTime[20];
  snprintf(isoTime, sizeof(isoTime), "2024-06-07T%02d:%02d:%02d+00:00", hours, minutes, seconds);
  return String(isoTime);
}
