from django.db import models


class CamMessage(models.Model):
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    station_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    generation_delta_time = models.PositiveIntegerField()
    station_type = models.PositiveIntegerField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude_m = models.FloatField(null=True, blank=True)
    speed_mps = models.FloatField(null=True, blank=True)
    heading_deg = models.FloatField(null=True, blank=True)
    drive_direction = models.CharField(max_length=32, blank=True)
    raw_hex = models.TextField()
    decoded = models.JSONField()

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"CAM {self.generation_delta_time} at {self.received_at:%H:%M:%S}"
