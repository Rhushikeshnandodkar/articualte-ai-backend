from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from .models import Interest, SubscriptionPlan, Badge, UserProfile, PaymentOrder, PlayPurchase


@admin.register(PlayPurchase)
class PlayPurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'product_id', 'expires_at', 'created_at')
    search_fields = ('user__username', 'user__email', 'product_id', 'order_id')
    readonly_fields = ('purchase_token', 'created_at', 'updated_at')


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'duration', 'plan_type', 'google_product_id')
    fieldsets = (
        (None, {'fields': ('name', 'price', 'duration', 'limit_minutes', 'plan_type', 'google_product_id')}),
        ('Description', {'fields': ('description',)}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'description':
            formfield.widget.attrs['style'] = 'min-height: 180px; font-family: monospace;'
            formfield.help_text = mark_safe(
                "You can paste HTML here (e.g. &lt;strong&gt;bold&lt;/strong&gt;, &lt;ul&gt;&lt;li&gt;bullets&lt;/li&gt;&lt;/ul&gt;). "
                "It will be rendered as rich text on the subscriptions page."
            )
        return formfield


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'score_threshold', 'created_at')
    search_fields = ('name',)


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ('razorpay_order_id', 'user', 'plan', 'status', 'amount_paise', 'created_at')
    list_filter = ('status',)
    search_fields = ('razorpay_order_id', 'razorpay_payment_id', 'user__username')
    raw_id_fields = ('user', 'plan')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'profession', 'goal', 'communication_level', 'created_at')
    list_filter = ('profession', 'goal', 'communication_level')
    search_fields = ('user__username', 'bio')
    filter_horizontal = ('interests', 'badges')
    raw_id_fields = ('user',)
