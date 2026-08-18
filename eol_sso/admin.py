from django.contrib import admin
from .models import UserIndivId

# Register your models here.
class IndivIdTableAdmin(admin.ModelAdmin):
    raw_id_fields = ('user',)
    list_display = ('indiv_id', 'user')
    search_fields = ['indiv_id', 'user__username', 'user__email']
    ordering = ['user__username']

admin.site.register(UserIndivId, IndivIdTableAdmin)
