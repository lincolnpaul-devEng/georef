from django.contrib import admin
from .models import ProcessedMap, UserAccess


@admin.register(UserAccess)
class UserAccessAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_approved', 'requested_at', 'approved_at')
    list_filter = ('is_approved', 'requested_at')
    search_fields = ('email', 'notes')
    actions = ['approve_selected_users']

    def approve_selected_users(self, request, queryset):
        queryset.update(is_approved=True)
    approve_selected_users.short_description = "Approve access for selected users"


@admin.register(ProcessedMap)
class ProcessedMapAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'status', 'datum', 'utm_zone', 'created_at')
    list_filter = ('status', 'datum', 'created_at')
    search_fields = ('title', 'error_message')
