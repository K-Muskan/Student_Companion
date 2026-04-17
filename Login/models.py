from django.db import models

# Create your models here.
#data base schema can be defined here
# After defining models, run the following commands to create migrations and apply them:
# python manage.py makemigrations
# python manage.py migrate



from django.db import models
from django.contrib.auth.models import User


class UserActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    activity_date = models.DateField()
    logged_in_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Login_useractivitylog'
        unique_together = ('user', 'activity_date')

    def __str__(self):
        return f"{self.user.username} - {self.activity_date}"


class DownloadLog(models.Model):
    DOWNLOAD_TYPES = [
        ('pdf', 'PDF Report'),
        ('json', 'JSON Data'),
        ('txt', 'Text Report'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assessment_id = models.BigIntegerField()
    download_type = models.CharField(max_length=10, choices=DOWNLOAD_TYPES)
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Login_downloadlog'

    def __str__(self):
        return f"{self.user.username} - {self.download_type} - {self.downloaded_at}"