from django.contrib.auth.models import User
from django.db import models

class UserSso(models.Model):
    indiv_id = models.CharField(max_length=20, unique=True, db_index=True)
    id_persona = models.IntegerField(unique=True, db_index=True, null=True, blank=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True, db_index=True)
