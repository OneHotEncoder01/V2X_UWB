from django.urls import path

from messages import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("station/<str:station_key>/", views.station_detail, name="station_detail"),
    path("api/messages/", views.messages_api, name="messages_api"),
    path("api/stations/", views.stations_api, name="stations_api"),
    path("api/latest/", views.latest_api, name="latest_api"),
    path("tiles/<int:z>/<int:x>/<int:y>.png", views.map_tile, name="map_tile"),
]
