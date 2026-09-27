# GIFTWEB_FINAL_PACKAGE_V1
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from .models import Product, Order

User=settings.AUTH_USER_MODEL

class Wishlist(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='wishlist_items')
    product=models.ForeignKey(Product,on_delete=models.CASCADE,related_name='wishlists')
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=('-created_at',)
        constraints=[models.UniqueConstraint(fields=('user','product'),name='unique_wishlist_user_product')]

class Review(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='product_reviews')
    product=models.ForeignKey(Product,on_delete=models.CASCADE,related_name='reviews')
    rating=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)])
    title=models.CharField(max_length=120,blank=True)
    body=models.TextField(max_length=2000)
    is_approved=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=('-created_at',)
        constraints=[models.UniqueConstraint(fields=('user','product'),name='unique_review_user_product')]

class Coupon(models.Model):
    PERCENT='percent'; FIXED='fixed'
    code=models.CharField(max_length=50,unique=True)
    kind=models.CharField(max_length=10,choices=((PERCENT,'درصدی'),(FIXED,'مبلغ ثابت')),default=PERCENT)
    value=models.PositiveIntegerField()
    min_order_amount=models.PositiveIntegerField(default=0)
    usage_limit=models.PositiveIntegerField(null=True,blank=True)
    used_count=models.PositiveIntegerField(default=0)
    starts_at=models.DateTimeField(null=True,blank=True)
    ends_at=models.DateTimeField(null=True,blank=True)
    is_active=models.BooleanField(default=True)
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.kind==self.PERCENT and self.value>100: raise ValidationError({'value':'درصد باید بین ۰ و ۱۰۰ باشد.'})
    @property
    def is_valid_now(self):
        n=timezone.now()
        return self.is_active and (not self.starts_at or n>=self.starts_at) and (not self.ends_at or n<=self.ends_at) and (self.usage_limit is None or self.used_count<self.usage_limit)
    def discount_for(self,amount):
        if amount<self.min_order_amount or not self.is_valid_now:return 0
        return min(amount,amount*self.value//100 if self.kind==self.PERCENT else self.value)

class CouponRedemption(models.Model):
    coupon=models.ForeignKey(Coupon,on_delete=models.PROTECT,related_name='redemptions')
    order=models.OneToOneField(Order,on_delete=models.CASCADE,related_name='coupon_redemption')
    user=models.ForeignKey(User,on_delete=models.PROTECT,related_name='coupon_redemptions')
    amount=models.PositiveIntegerField(default=0)
    created_at=models.DateTimeField(auto_now_add=True)

class Referral(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name='referral_profile')
    code=models.CharField(max_length=32,unique=True)
    referred_by=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='referrals')
    created_at=models.DateTimeField(auto_now_add=True)

class LoyaltyAccount(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name='loyalty')
    points=models.PositiveIntegerField(default=0)
    lifetime_points=models.PositiveIntegerField(default=0)
    updated_at=models.DateTimeField(auto_now=True)

class LoyaltyTransaction(models.Model):
    account=models.ForeignKey(LoyaltyAccount,on_delete=models.CASCADE,related_name='transactions')
    points=models.IntegerField()
    reason=models.CharField(max_length=160)
    order=models.ForeignKey(Order,on_delete=models.SET_NULL,null=True,blank=True,related_name='loyalty_transactions')
    created_at=models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='notifications')
    title=models.CharField(max_length=160)
    body=models.TextField(blank=True)
    is_read=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=('-created_at',)

class RecentlyViewed(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,null=True,blank=True,related_name='recently_viewed')
    session_key=models.CharField(max_length=40,blank=True,db_index=True)
    product=models.ForeignKey(Product,on_delete=models.CASCADE,related_name='recent_views')
    viewed_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=('-viewed_at',)
