from django.contrib import admin
from .models import UserSso


# Register your models here.
class PhTableAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    list_display = ('indiv_id', 'id_persona', 'user')
    search_fields = ['indiv_id', 'id_persona', 'user__username', 'user__email']
    ordering = ['user__username']

class IndivIdTableAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    list_display = ('indiv_id', 'user')
    search_fields = ['indiv_id', 'user__username', 'user__email']
    ordering = ['user__username']

admin.site.register(UserSso, PhTableAdmin)
